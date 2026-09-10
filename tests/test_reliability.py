from __future__ import annotations

import unittest
from unittest.mock import Mock, call, patch
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import httpx

from sangam import (
    captions, consensus, daily, db, discover, evaluate, extract, ingest, normalize, prices,
)
from sangam.outcome import StageResult


class HttpRetryTests(unittest.TestCase):
    @patch("sangam.db.random.uniform", return_value=1.0)
    @patch("sangam.db.time.sleep")
    @patch("sangam.db._CLIENT.request")
    def test_retries_transient_http_status(self, request, sleep, _uniform):
        req = httpx.Request("GET", "https://example.test/feed")
        request.side_effect = [
            httpx.Response(503, request=req),
            httpx.Response(200, request=req, content=b"ok"),
        ]

        response = db._do("GET", str(req.url))

        self.assertEqual(200, response.status_code)
        self.assertEqual(2, request.call_count)
        sleep.assert_called_once()

    @patch("sangam.db._do")
    def test_feed_fetch_rejects_http_errors(self, do):
        do.return_value = httpx.Response(
            404, request=httpx.Request("GET", "https://example.test/feed")
        )
        with self.assertRaises(httpx.HTTPStatusError):
            db.fetch_feed("https://example.test/feed")


class BrokerAuthTests(unittest.TestCase):
    """The broker-instruments project scopes its RLS policy to one dedicated
    Auth identity, not to anon — so fetching from it means signing in as that
    user first, not just sending an anon key. See db._broker_auth_token."""

    def test_returns_none_when_unconfigured(self):
        with patch.multiple(
            "sangam.db.config",
            BROKER_SUPABASE_URL="", BROKER_SUPABASE_ANON_KEY=None,
            BROKER_SUPABASE_EMAIL=None, BROKER_SUPABASE_PASSWORD=None,
        ):
            self.assertIsNone(db._broker_auth_token())

    @patch("sangam.db._do")
    def test_signs_in_with_password_grant_and_returns_access_token(self, do):
        do.return_value = httpx.Response(
            200,
            request=httpx.Request("POST", "https://broker.test/auth/v1/token"),
            json={"access_token": "jwt-for-sangam-service-user"},
        )
        with patch.multiple(
            "sangam.db.config",
            BROKER_SUPABASE_URL="https://broker.test", BROKER_SUPABASE_ANON_KEY="anon-key",
            BROKER_SUPABASE_EMAIL="sangam@service.test", BROKER_SUPABASE_PASSWORD="secret",
        ):
            token = db._broker_auth_token()

        self.assertEqual("jwt-for-sangam-service-user", token)
        _, kwargs = do.call_args
        self.assertEqual("anon-key", kwargs["headers"]["apikey"])
        self.assertEqual(
            {"email": "sangam@service.test", "password": "secret"}, kwargs["json"]
        )

    @patch("sangam.db._broker_auth_token", return_value=None)
    def test_fetch_broker_instruments_skips_request_without_a_token(self, _auth):
        self.assertEqual([], db.fetch_broker_instruments())

    @patch("sangam.db._do")
    @patch("sangam.db._broker_auth_token", return_value="jwt-for-sangam-service-user")
    def test_fetch_broker_instruments_uses_the_signed_in_token_not_the_anon_key(
        self, _auth, do
    ):
        do.return_value = httpx.Response(
            200,
            request=httpx.Request("GET", "https://broker.test/rest/v1/broker_instruments_public"),
            json=[{"exchange": "NSE", "symbol": "RELIANCE"}],
        )
        with patch.multiple(
            "sangam.db.config",
            BROKER_SUPABASE_URL="https://broker.test", BROKER_SUPABASE_ANON_KEY="anon-key",
        ):
            rows = db.fetch_broker_instruments()

        self.assertEqual([{"exchange": "NSE", "symbol": "RELIANCE"}], rows)
        _, kwargs = do.call_args
        self.assertEqual("Bearer jwt-for-sangam-service-user", kwargs["headers"]["Authorization"])
        self.assertEqual("anon-key", kwargs["headers"]["apikey"])
        self.assertIn("broker_instruments_public", do.call_args.args[1])


class CaptionStateTests(unittest.TestCase):
    @patch("sangam.captions.db.save_transcript")
    @patch("sangam.captions.db.retry_at", return_value="later")
    @patch("sangam.captions.db.videos_needing_captions", return_value=[("v1", "Video", 0)])
    @patch("sangam.captions.fetch_caption", side_effect=RuntimeError("blocked"))
    @patch("sangam.captions._api")
    def test_transient_caption_failure_is_retryable(
        self, _api, _fetch, _pending, _retry_at, save
    ):
        result = captions.run()

        self.assertFalse(result.ok)
        save.assert_called_once_with(
            None,
            "v1",
            None,
            None,
            "retry",
            attempts=1,
            error="blocked",
            next_retry_at="later",
        )

    @patch("sangam.captions.db.save_transcript")
    @patch("sangam.captions.db.videos_needing_captions", return_value=[("v1", "Video", 0)])
    @patch("sangam.captions.fetch_caption", side_effect=captions.CaptionUnavailable("disabled"))
    @patch("sangam.captions._api")
    def test_permanent_caption_failure_is_unavailable(self, _api, _fetch, _pending, save):
        result = captions.run()

        self.assertTrue(result.ok)
        save.assert_called_once_with(
            None,
            "v1",
            None,
            None,
            "unavailable",
            attempts=1,
            error="disabled",
        )

    def test_private_video_is_permanently_unavailable(self):
        api = Mock()
        api.list.side_effect = captions.VideoUnplayable(
            "v1", "This video is private", []
        )

        with self.assertRaisesRegex(captions.CaptionUnavailable, "video is private"):
            captions.fetch_caption(api, "v1")

    @patch("sangam.captions.db.save_transcript")
    @patch("sangam.captions.db.retry_at", return_value="later")
    @patch(
        "sangam.captions.db.videos_needing_captions",
        return_value=[("v1", "First", 0), ("v2", "Second", 0)],
    )
    @patch(
        "sangam.captions.fetch_caption",
        side_effect=captions.CaptionAccessBlocked("configure SANGAM_PROXY_URL"),
    )
    @patch("sangam.captions._api")
    def test_host_block_pauses_remaining_caption_batch(
        self, _api, fetch, _pending, _retry_at, save
    ):
        result = captions.run()

        self.assertFalse(result.ok)
        self.assertEqual(1, result.processed)
        fetch.assert_called_once()
        save.assert_called_once_with(
            None,
            "v1",
            None,
            None,
            "retry",
            attempts=1,
            error="configure SANGAM_PROXY_URL",
            next_retry_at="later",
        )

    @patch("sangam.captions.db.save_transcript")
    @patch(
        "sangam.captions.db.videos_needing_captions",
        return_value=[
            ("v1", "Blocked", 1, None),
            ("v2", "Private", 2, "The video is unplayable: This video is private"),
        ],
    )
    @patch(
        "sangam.captions.fetch_caption",
        side_effect=captions.CaptionAccessBlocked("IP blocked"),
    )
    @patch("sangam.captions.db.retry_at", return_value="later")
    @patch("sangam.captions._api")
    def test_saved_private_failure_is_closed_before_host_block(
        self, _api, _retry, fetch, _pending, save
    ):
        result = captions.run()

        self.assertFalse(result.ok)
        self.assertEqual(2, result.processed)
        fetch.assert_called_once()
        self.assertIn(
            call(
                None, "v2", None, None, "unavailable",
                attempts=2, error="This video is private",
            ),
            save.call_args_list,
        )

    def test_caption_selection_prefers_configured_language(self):
        class Track:
            def __init__(self, language_code, generated, text):
                self.language_code = language_code
                self.is_generated = generated
                self._text = text

            def fetch(self):
                fetched = Mock()
                fetched.to_raw_data.return_value = [{"text": self._text}]
                return fetched

        api = Mock()
        api.list.return_value = [
            Track("fr", False, "French manual"),
            Track("hi", True, "Hindi generated"),
        ]

        self.assertEqual("Hindi generated", captions.fetch_caption(api, "v1"))


class DiscoveryStateTests(unittest.TestCase):
    @patch(
        "sangam.discover.db.insert_videos_if_new",
        side_effect=lambda _conn, videos: videos,
    )
    @patch("sangam.discover.db.fetch_feed", return_value=b"feed")
    @patch("sangam.discover.config.feeds_for", return_value=["canonical"])
    @patch("sangam.discover.db.get_channels", return_value=[{"channel_id": "c1", "name": "Creator"}])
    def test_canonical_feed_uses_channel_watermark_and_batch_insert(
        self, _channels, feeds, fetch, insert
    ):
        now = datetime.now(timezone.utc)
        entry_time = now - timedelta(days=2)
        entry = {
            "id": "yt:v1",
            "title": "Video",
            "summary": "Description",
            "link": "https://youtube.test/v1",
        }
        entry = SimpleNamespace(
            **entry,
            published_parsed=entry_time.utctimetuple(),
            yt_videoid="v1",
            get=lambda key, default=None: getattr(entry, key, default),
        )
        feed = SimpleNamespace(entries=[entry], bozo=False)

        with patch(
            "sangam.discover.db.discovery_watermarks",
            return_value={"c1": now - timedelta(days=3)},
        ), patch("sangam.discover.feedparser.parse", return_value=feed):
            result = discover.discover()

        self.assertTrue(result.ok)
        self.assertEqual(1, result.count)
        feeds.assert_called_once_with("c1")
        fetch.assert_called_once_with("canonical")
        insert.assert_called_once()

    def test_short_classification_uses_feed_metadata_hints(self):
        regular = {"link": "https://youtube.test/watch?v=v1", "title": "Video"}
        short = {
            "link": "https://youtube.test/watch?v=v2",
            "title": "Quick update #Shorts",
        }

        self.assertFalse(discover._looks_short(regular))
        self.assertTrue(discover._looks_short(short))

    def test_uploads_page_parser_reads_current_lockup_shape(self):
        now = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
        initial_data = {
            "contents": [{
                "lockupViewModel": {
                    "contentId": "v1",
                    "contentType": "LOCKUP_CONTENT_TYPE_VIDEO",
                    "metadata": {"lockupMetadataViewModel": {
                        "title": {"content": "Market update"},
                        "metadata": {"contentMetadataViewModel": {
                            "metadataRows": [{"metadataParts": [
                                {"text": {"content": "100 views"}},
                                {"text": {"content": "5 hours ago"}},
                            ]}]
                        }},
                    }},
                }
            }]
        }
        page = f"<script>var ytInitialData = {__import__('json').dumps(initial_data)};</script>"

        with patch("sangam.discover.db.fetch_youtube_page", return_value=page.encode()):
            entries = discover._uploads_page_entries("creator", now)

        self.assertEqual(1, len(entries))
        self.assertEqual("v1", entries[0]["video_id"])
        self.assertEqual(now - timedelta(hours=5), entries[0]["published_at"])

    @patch(
        "sangam.discover.db.insert_videos_if_new",
        side_effect=lambda _conn, videos: videos,
    )
    @patch("sangam.discover._uploads_page_entries")
    @patch("sangam.discover.db.fetch_feed", side_effect=RuntimeError("RSS down"))
    @patch("sangam.discover.config.feeds_for", return_value=["canonical"])
    @patch(
        "sangam.discover.db.get_channels",
        return_value=[{"channel_id": "c1", "name": "Creator", "handle": "creator"}],
    )
    def test_rss_failure_uses_uploads_page_without_failing_stage(
        self, _channels, _feeds, _fetch, fallback, insert
    ):
        now = datetime.now(timezone.utc)
        fallback.return_value = [{
            "video_id": "v1",
            "title": "Video",
            "summary": None,
            "link": "https://youtube.test/watch?v=v1",
            "published_at": now - timedelta(hours=1),
            "is_short": False,
        }]
        with patch("sangam.discover.db.discovery_watermarks", return_value={}):
            result = discover.discover()

        self.assertTrue(result.ok)
        self.assertEqual(1, result.count)
        fallback.assert_called_once()
        insert.assert_called_once()


class ExtractionStateTests(unittest.TestCase):
    @patch("sangam.extract.normalize.resolve_record", return_value=None)
    @patch("sangam.extract._generate")
    def test_extraction_clamps_and_deduplicates_mentions(self, generate, _resolve):
        mention = {
            "raw_mention": " RIL ",
            "instrument_type": "stock",
            "action": "buy",
            "conviction": 9,
            "confidence": -1,
            "note": "note",
            "long_note": "long",
            "evidence": "evidence",
        }
        generate.return_value = {"summary": " summary ", "mentions": [mention, mention]}

        summary, rows, source = extract._extract_one("Video", "done", "text", None)

        self.assertEqual("summary", summary)
        self.assertEqual("transcript", source)
        self.assertEqual(1, len(rows))
        self.assertEqual(5, rows[0]["conviction"])
        self.assertEqual(0.0, rows[0]["confidence"])

    @patch("sangam.extract.db.save_extraction")
    @patch("sangam.extract.db.retry_at", return_value="later")
    @patch(
        "sangam.extract.db.videos_needing_extract",
        return_value=[("v1", "Video", "done", "text", "description", 0)],
    )
    @patch("sangam.extract._extract_one", side_effect=RuntimeError("quota"))
    def test_transient_extraction_failure_is_retryable(
        self, _extract, _pending, _retry_at, save
    ):
        result = extract.run()

        self.assertFalse(result.ok)
        save.assert_called_once_with(
            None,
            "v1",
            None,
            "retry",
            attempts=1,
            error="quota",
            next_retry_at="later",
        )

    @patch("sangam.extract.db.save_extraction")
    @patch("sangam.extract.db.replace_extraction")
    @patch(
        "sangam.extract.db.videos_needing_extract",
        return_value=[("v1", "Video", "done", "text", "description", 1)],
    )
    @patch("sangam.extract._extract_one", return_value=("summary", [{"raw_mention": "RIL"}], "transcript"))
    def test_success_uses_atomic_replacement(self, _extract, _pending, replace, save):
        result = extract.run()

        self.assertTrue(result.ok)
        self.assertEqual(1, result.count)
        replace.assert_called_once_with(
            None, "v1", "summary", [{"raw_mention": "RIL"}], "transcript", 2
        )
        save.assert_not_called()


class NormalizationTests(unittest.TestCase):
    def setUp(self):
        # These lookups cache for the process lifetime; reset them so one
        # test's mocked fixture can't leak into another's.
        normalize._broker_lookup_cache = None
        normalize._broker_prefix_cache = None
        normalize._nse_lookup_cache = None
        normalize._nse_prefix_cache = None

    def test_aliases_merge_to_one_symbol(self):
        self.assertEqual("RELIANCE", normalize.resolve("RIL", "stock"))
        self.assertEqual("RELIANCE", normalize.resolve("Reliance Industries", "stock"))

    def test_obvious_type_error_is_corrected(self):
        result = normalize.resolve_record("Nifty 50", "stock")
        self.assertIsNotNone(result)
        self.assertEqual(("INDEX:NIFTY_50", "sector"), (result.symbol, result.instrument_type))

    @patch("sangam.db.fetch_nse_equity_list", return_value=[])
    @patch("sangam.db.fetch_broker_instruments", return_value=[])
    def test_ambiguous_and_generic_names_are_not_forced(self, _broker, _nse):
        self.assertIsNone(normalize.resolve("Tata", "stock"))
        self.assertIsNone(normalize.resolve("mutual funds", "mutual_fund"))

    @patch("sangam.db.fetch_broker_instruments")
    def test_broker_master_resolves_names_missing_from_curated_aliases(self, fetch):
        fetch.return_value = [{
            "exchange": "NSE", "symbol": "TATACONSUM", "name": "TATA CONSUMER PRODUCTS LTD",
            "instrument_type": "EQ", "trading_symbol": "TATACONSUM-EQ",
        }]

        self.assertEqual("TATACONSUM", normalize.resolve("Tata Consumer Products Ltd", "stock"))

    @patch("sangam.db.fetch_broker_instruments")
    def test_broker_master_prefers_nse_on_name_collision_with_bse(self, fetch):
        fetch.return_value = [
            {"exchange": "BSE", "symbol": "500408", "name": "TATA POWER",
             "instrument_type": "EQ", "trading_symbol": "TATAPOWER"},
            {"exchange": "NSE", "symbol": "TATAPOWER", "name": "TATA POWER",
             "instrument_type": "EQ", "trading_symbol": "TATAPOWER-EQ"},
        ]

        self.assertEqual("TATAPOWER", normalize.resolve("Tata Power", "stock"))

    @patch("sangam.db.fetch_broker_instruments")
    def test_broker_master_matches_despite_registered_legal_suffix(self, fetch):
        # A transcript says "Acme Solar"; the broker master's registered
        # name carries the legal suffix the speaker never says out loud.
        fetch.return_value = [{
            "exchange": "NSE", "symbol": "ACMESOLAR", "name": "Acme Solar Holdings Limited",
            "instrument_type": "EQ", "trading_symbol": "ACMESOLAR-EQ",
        }]

        self.assertEqual("ACMESOLAR", normalize.resolve("Acme Solar Holdings", "stock"))

    @patch("sangam.db.fetch_nse_equity_list", return_value=[])
    @patch("sangam.db.fetch_broker_instruments")
    def test_broker_master_ignores_non_equity_rows(self, fetch, _nse):
        fetch.return_value = [{
            "exchange": "NSE", "symbol": "Nifty Bank", "name": "NIFTY BANK",
            "instrument_type": "AMXIDX", "trading_symbol": "Nifty Bank",
        }]

        self.assertIsNone(normalize.resolve("Nifty Bank", "stock"))

    @patch("sangam.db.fetch_nse_equity_list", return_value=[])
    @patch("sangam.db.fetch_broker_instruments", side_effect=RuntimeError("network down"))
    def test_broker_master_failure_degrades_to_unresolved(self, _fetch, _nse):
        self.assertIsNone(normalize.resolve("Some Unlisted Co", "stock"))

    @patch("sangam.db.fetch_broker_instruments", return_value=[])
    def test_nse_list_resolves_names_missing_from_other_sources(self, _broker):
        with patch("sangam.db.fetch_nse_equity_list", return_value=[
            {"symbol": "MAZDOCK", "name": "MAZAGON DOCK SHIPBUILDERS LIMITED"},
        ]):
            self.assertEqual("MAZDOCK", normalize.resolve("Mazagon Dock Shipbuilders", "stock"))

    @patch("sangam.db.fetch_broker_instruments", return_value=[])
    @patch("sangam.db.fetch_nse_equity_list", side_effect=RuntimeError("nse archives unreachable"))
    def test_nse_list_failure_degrades_to_unresolved(self, _nse, _broker):
        self.assertIsNone(normalize.resolve("Some Other Unlisted Co", "stock"))

    @patch("sangam.db.fetch_broker_instruments", return_value=[])
    def test_prefix_match_fills_in_a_dropped_trailing_word(self, _broker):
        # A transcript says "Happiest Minds"; the registered name has an
        # extra word ("Technologies") the mention never said.
        with patch("sangam.db.fetch_nse_equity_list", return_value=[
            {"symbol": "HAPPSTMNDS", "name": "Happiest Minds Technologies Limited"},
        ]):
            self.assertEqual("HAPPSTMNDS", normalize.resolve("Happiest Minds", "stock"))

    @patch("sangam.db.fetch_broker_instruments", return_value=[])
    def test_prefix_match_refuses_when_more_than_one_candidate_matches(self, _broker):
        with patch("sangam.db.fetch_nse_equity_list", return_value=[
            {"symbol": "ADANIPOWER", "name": "Adani Power Limited"},
            {"symbol": "ADANIENT", "name": "Adani Enterprises Limited"},
        ]):
            self.assertIsNone(normalize.resolve("Adani", "stock"))

    @patch("sangam.db.fetch_broker_instruments", return_value=[])
    def test_prefix_match_does_not_fire_on_a_single_word_mention(self, _broker):
        # Even with only one candidate present, a single-word mention should
        # never prefix-match — too easy for a common short word to
        # coincidentally prefix an unrelated company (this guards the case
        # above even if only one Adani-group company happened to be listed).
        with patch("sangam.db.fetch_nse_equity_list", return_value=[
            {"symbol": "ADANIPOWER", "name": "Adani Power Limited"},
        ]):
            self.assertIsNone(normalize.resolve("Adani", "stock"))

    def test_unresolved_report_ranks_by_frequency_and_omits_one_offs(self):
        rows = [
            {"raw_mention": "Kanohar Electricals", "resolved_symbol": None, "instrument_type": "stock"},
            {"raw_mention": "kanohar electricals", "resolved_symbol": None, "instrument_type": "stock"},
            {"raw_mention": "Kanohar Electricals", "resolved_symbol": None, "instrument_type": "stock"},
            {"raw_mention": "Some Rare Co", "resolved_symbol": None, "instrument_type": "stock"},
            {"raw_mention": "Reliance Industries", "resolved_symbol": "RELIANCE", "instrument_type": "stock"},
            {"raw_mention": "Nifty 50", "resolved_symbol": None, "instrument_type": "sector"},
            {"raw_mention": "mutual funds", "resolved_symbol": None, "instrument_type": "mutual_fund"},
        ]

        report = normalize.unresolved_report(rows)

        self.assertEqual(
            [{"raw_mention": "Kanohar Electricals", "count": 3}], report
        )

    @patch(
        "sangam.db.mentions_for_normalization",
        return_value=[
            {"raw_mention": "Kanohar Electricals", "resolved_symbol": None, "instrument_type": "stock"},
            {"raw_mention": "Kanohar Electricals", "resolved_symbol": None, "instrument_type": "stock"},
        ],
    )
    def test_ingest_unresolved_stage_reports_via_normalize(self, _mentions):
        result = ingest.run_unresolved()

        self.assertEqual(StageResult("unresolved", 1, 2), result)

    @patch("sangam.db.fetch_nse_equity_list", return_value=[])
    @patch("sangam.db.fetch_broker_instruments", return_value=[])
    def test_snapshot_evaluation_meets_quality_gate(self, _broker, _nse):
        # The quality gate exercises deterministic, reviewed matching (curated
        # aliases) — it must not depend on live external data sources that can
        # change independently of this code and make the gate flaky.
        metrics = evaluate.evaluate()

        self.assertEqual([], metrics["failures"])
        self.assertGreaterEqual(metrics["precision"], 0.9)
        self.assertGreaterEqual(metrics["recall"], 0.9)


class ConsensusAndDailyTests(unittest.TestCase):
    @staticmethod
    def _mention(channel, action, confidence, *, source="transcript", published="2026-09-01T08:00:00+00:00"):
        return {
            "id": hash((channel, action, confidence)),
            "video_id": f"v-{channel}-{action}",
            "raw_mention": "Reliance Industries",
            "resolved_symbol": "RELIANCE",
            "instrument_type": "stock",
            "action": action,
            "conviction": 4,
            "confidence": confidence,
            "source": source,
            "note": f"{action} note",
            "video": {
                "channel_id": channel,
                "published_at": published,
                "channel": {"name": channel},
            },
        }

    def test_consensus_weights_each_creator_once_and_excludes_description(self):
        rows = [
            self._mention("A", "buy", 0.7),
            self._mention("A", "hold", 0.95),
            self._mention("B", "sell", 0.8),
            self._mention("C", "buy", 0.99, source="description"),
        ]

        item = consensus.build(rows)[0]

        self.assertEqual(2, item["creator_count"])
        self.assertEqual(3, item["mention_count"])
        self.assertEqual({"hold": 1, "sell": 1}, item["action_counts"])

    @patch("sangam.daily.render_video", return_value=None)
    @patch("sangam.daily.db.recent_mentions_for_report")
    def test_daily_package_contains_machine_and_human_outputs(self, recent, _render):
        now = datetime(2026, 9, 1, 12, tzinfo=timezone.utc)
        recent.return_value = [self._mention("A", "buy", 0.9)]
        with TemporaryDirectory() as temp:
            directory, video = daily.generate(
                out_root=Path(temp), hours=24, max_items=5, now=now, min_creators=1
            )

            self.assertIsNone(video)
            self.assertTrue((directory / "brief.json").exists())
            brief = __import__("json").loads((directory / "brief.json").read_text())
            self.assertEqual("RELIANCE", brief["items"][0]["name"])
            self.assertTrue(brief["items"][0]["resolved"])
            self.assertIn("RELIANCE", (directory / "brief.md").read_text())
            self.assertIn("not investment advice", (directory / "captions.srt").read_text())


class PriceTests(unittest.TestCase):
    def test_yahoo_ticker_maps_by_symbol_namespace(self):
        self.assertEqual("RELIANCE.NS", prices.yahoo_ticker("RELIANCE"))
        self.assertEqual("NVDA", prices.yahoo_ticker("NASDAQ:NVDA"))
        self.assertEqual("WMT", prices.yahoo_ticker("NYSE:WMT"))
        self.assertIsNone(prices.yahoo_ticker("SECTOR:IT"))
        self.assertIsNone(prices.yahoo_ticker("MF:HDFC_FLEXI_CAP"))

    def test_is_trading_day_excludes_weekend(self):
        self.assertTrue(prices.is_trading_day(datetime(2026, 9, 9, tzinfo=timezone.utc)))   # Wed
        self.assertFalse(prices.is_trading_day(datetime(2026, 9, 13, tzinfo=timezone.utc)))  # Sun

    @patch("sangam.prices.db.fetch_external")
    def test_fetch_history_skips_null_sessions(self, fetch_external):
        fetch_external.return_value = httpx.Response(
            200,
            request=httpx.Request("GET", "https://example.test/chart/RELIANCE.NS"),
            json={
                "chart": {
                    "result": [{
                        "timestamp": [1757347800, 1757434200],
                        "indicators": {"quote": [{"close": [1402.5, None]}]},
                    }]
                }
            },
        )

        result = prices.fetch_history("RELIANCE.NS")

        self.assertEqual([("2025-09-08", 1402.5)], result)

    @patch("sangam.prices.db.fetch_external")
    def test_fetch_history_returns_empty_on_404(self, fetch_external):
        fetch_external.return_value = httpx.Response(
            404, request=httpx.Request("GET", "https://example.test/chart/BAD.NS")
        )

        self.assertEqual([], prices.fetch_history("BAD.NS"))

    def test_run_skips_outside_trading_days(self):
        with patch("sangam.prices.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 9, 13, tzinfo=timezone.utc)  # Sunday
            mock_dt.fromtimestamp = datetime.fromtimestamp
            result = prices.run()

        self.assertEqual(StageResult("prices", 0, 0), result)

    @patch("sangam.prices.db.upsert_price_points", return_value=2)
    @patch("sangam.prices.db.symbols_needing_prices", return_value=["RELIANCE", "SECTOR:IT"])
    @patch(
        "sangam.prices.fetch_history",
        return_value=[("2026-09-08", 1390.0), ("2026-09-09", 1400.0)],
    )
    def test_run_prices_only_priceable_symbols_on_a_trading_day(
        self, fetch_history, _symbols, upsert
    ):
        with patch("sangam.prices.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 9, 9, tzinfo=timezone.utc)  # Wednesday

            result = prices.run()

        fetch_history.assert_called_once_with("RELIANCE.NS")
        upsert.assert_called_once_with(
            None,
            [
                {"symbol": "RELIANCE", "price_date": "2026-09-08", "close": 1390.0},
                {"symbol": "RELIANCE", "price_date": "2026-09-09", "close": 1400.0},
            ],
        )
        self.assertEqual(StageResult("prices", 1, 2), result)


class RunHealthTests(unittest.TestCase):
    @patch("sangam.db._do")
    def test_start_run_explicitly_writes_start_timestamp(self, do):
        response = Mock()
        response.json.return_value = [{"id": 7}]
        do.return_value = response

        self.assertEqual(7, db.start_run())

        payload = do.call_args.kwargs["json"]
        started_at = datetime.fromisoformat(payload["started_at"])
        self.assertIsNotNone(started_at.tzinfo)
        self.assertEqual("running", payload["status"])

    @patch("sangam.ingest.db.finish_run")
    @patch("sangam.ingest.db.start_run", return_value=42)
    @patch("sangam.ingest.db.init_schema")
    @patch("sangam.ingest.extract.run", return_value=StageResult("extract", 3, 1))
    @patch(
        "sangam.ingest.captions.run",
        return_value=StageResult("captions", 1, 2, ["one blocked caption"]),
    )
    @patch("sangam.ingest.discover.discover", return_value=StageResult("discover", 2, 2))
    def test_partial_run_is_recorded_and_reported(
        self, _discover, _captions, _extract, _init, _start, finish
    ):
        result = ingest.run_all()

        self.assertFalse(result.ok)
        finish.assert_called_once_with(
            42,
            "partial",
            new_videos=2,
            transcribed=1,
            mentions=3,
            error="one blocked caption",
        )


if __name__ == "__main__":
    unittest.main()
