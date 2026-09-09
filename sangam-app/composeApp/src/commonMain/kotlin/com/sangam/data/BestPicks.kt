package com.sangam.data

import com.sangam.model.ConsensusItem

private val BULLISH_ACTIONS = setOf("buy", "future_opportunity", "wait_for_dip")

/**
 * Net-bullish, multi-creator, high-conviction picks within a timeframe — the
 * ranked candidate feed for a watchlist. Pure filter+score over
 * buildConsensus() output, so it shares one grouping/dedup rule with the
 * Stocks/Sectors screens rather than re-deriving consensus its own way.
 */
fun bestPicks(items: List<ConsensusItem>): List<ConsensusItem> =
    items
        .filter { bullishCount(it) > 0 && bullishCount(it) >= bearishCount(it) }
        .sortedWith(compareByDescending<ConsensusItem> { pickScore(it) }.thenByDescending { it.avgConviction })

private fun bullishCount(item: ConsensusItem): Int =
    item.actionCounts.filterKeys { it in BULLISH_ACTIONS }.values.sum()

private fun bearishCount(item: ConsensusItem): Int = item.actionCounts["sell"] ?: 0

/** Breadth (distinct creators) dominates, conviction breaks ties, dissent penalizes. */
private fun pickScore(item: ConsensusItem): Double =
    item.channels * 2.0 + item.avgConviction - bearishCount(item) * 1.5
