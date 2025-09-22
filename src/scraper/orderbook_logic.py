"""
Orderbook analysis module for calculating weighted prices and spreads.

This module provides functionality to analyze cryptocurrency orderbooks,
calculate weighted average prices, and compute spreads at different volume levels.
"""

import json
from typing import Dict, List, Tuple, Optional
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass
from enum import Enum


class OrderSide(Enum):
    """Enumeration for order sides."""
    BUY = "buy"
    SELL = "sell"


@dataclass
class OrderLevel:
    """Represents a single price level in the orderbook."""
    price: Decimal
    quantity: Decimal

    @classmethod
    def from_strings(cls, price_str: str, quantity_str: str) -> 'OrderLevel':
        """Create OrderLevel from string representations."""
        return cls(
            price=Decimal(price_str),
            quantity=Decimal(quantity_str)
        )


@dataclass
class WeightedPriceResult:
    """Result of weighted price calculation."""
    weighted_price: Decimal
    actual_amount_filled: Decimal
    base_volume_traded: Decimal


@dataclass
class SpreadAnalysis:
    """Analysis results for a specific volume level."""
    level_quote: Decimal
    buy_price: Decimal
    sell_price: Decimal
    buy_filled_quote: Decimal
    sell_filled_quote: Decimal
    absolute_spread: Decimal
    relative_spread_pct: Decimal
    market_impact_buy_pct: Decimal
    market_impact_sell_pct: Decimal


@dataclass
class MarketSummary:
    """Summary of market conditions."""
    best_bid: Decimal
    best_ask: Decimal
    best_spread: Decimal
    best_spread_pct: Decimal
    market_id: str


class OrderbookAnalyzer:
    """Analyzer for orderbook data with improved architecture and error handling."""

    def __init__(self, precision: int = 8):
        """
        Initialize the analyzer.

        Args:
            precision: Decimal precision for calculations
        """
        self.precision = precision

    def get_weighted_price(
            self,
            orders: List[List[str]],
            target_amount: Decimal,
            is_buying: bool = True
    ) -> WeightedPriceResult:
        """
        Calculate weighted average price for a given quote amount.

        Args:
            orders: List of [price, quantity] pairs
            target_amount: Target amount in quote currency
            is_buying: True for buying (using asks), False for selling (using bids)

        Returns:
            WeightedPriceResult with calculated values

        Raises:
            ValueError: If target_amount is negative or orders are invalid
        """
        if target_amount <= 0:
            raise ValueError("Target amount must be positive")

        if not orders:
            return WeightedPriceResult(
                weighted_price=Decimal('0'),
                actual_amount_filled=Decimal('0'),
                base_volume_traded=Decimal('0')
            )

        remaining_quote = target_amount
        total_base_traded = Decimal('0')
        total_quote_spent = Decimal('0')

        try:
            order_levels = [OrderLevel.from_strings(price, qty) for price, qty in orders]
        except (ValueError, TypeError) as e:
            raise ValueError(f"Invalid order data: {e}")

        for level in order_levels:
            if remaining_quote <= 0:
                break

            if level.price <= 0 or level.quantity <= 0:
                continue  # Skip invalid levels

            # Maximum quote value available at this price level
            max_quote_at_level = level.price * level.quantity

            if remaining_quote >= max_quote_at_level:
                # Take the entire order level
                base_traded = level.quantity
                quote_spent = max_quote_at_level
                remaining_quote -= quote_spent
            else:
                # Partially fill this level
                base_traded = remaining_quote / level.price
                quote_spent = remaining_quote
                remaining_quote = Decimal('0')

            total_base_traded += base_traded
            total_quote_spent += quote_spent

        # Calculate weighted average price
        if total_base_traded > 0:
            weighted_price = total_quote_spent / total_base_traded
        else:
            weighted_price = Decimal('0')

        return WeightedPriceResult(
            weighted_price=self._round_decimal(weighted_price),
            actual_amount_filled=self._round_decimal(total_quote_spent),
            base_volume_traded=self._round_decimal(total_base_traded)
        )

    def calculate_spreads(
            self,
            market_orderbook: Dict,
            levels: List[float]
    ) -> Dict[str, Dict]:
        """
        Calculate spreads at different quote currency levels from order book data.

        Args:
            market_orderbook: Dictionary containing 'asks' and 'bids' data
            levels: List of quote amounts to calculate spreads for

        Returns:
            Dictionary with spread analysis for each level

        Raises:
            ValueError: If orderbook data is invalid
        """
        if not isinstance(market_orderbook, dict):
            raise ValueError("market_orderbook must be a dictionary")

        if 'asks' not in market_orderbook or 'bids' not in market_orderbook:
            raise ValueError("Orderbook must contain 'asks' and 'bids' keys")

        asks = market_orderbook['asks']  # Sell orders (ascending price)
        bids = market_orderbook['bids']  # Buy orders (descending price)

        if not asks or not bids:
            raise ValueError("Orderbook must have non-empty asks and bids")

        results = {}

        # Get best bid and ask for reference
        try:
            best_ask = Decimal(asks[0][0]) if asks else Decimal('0')
            best_bid = Decimal(bids[0][0]) if bids else Decimal('0')
        except (ValueError, IndexError) as e:
            raise ValueError(f"Invalid orderbook format: {e}")

        for level in levels:
            level_decimal = Decimal(str(level))

            # Calculate buy price (using asks - we're buying from sellers)
            buy_result = self.get_weighted_price(asks, level_decimal, True)

            # Calculate sell price (using bids - we're selling to buyers)
            sell_result = self.get_weighted_price(bids, level_decimal, False)

            # Calculate spread metrics
            spread_analysis = self._calculate_spread_metrics(
                buy_result, sell_result, best_ask, best_bid, level_decimal
            )

            results[f"{level:.0f}_QUOTE"] = spread_analysis.__dict__

        # Add market summary
        results['market_summary'] = self._create_market_summary(
            market_orderbook, best_bid, best_ask
        ).__dict__

        return results

    def _calculate_spread_metrics(
            self,
            buy_result: WeightedPriceResult,
            sell_result: WeightedPriceResult,
            best_ask: Decimal,
            best_bid: Decimal,
            level: Decimal
    ) -> SpreadAnalysis:
        """Calculate spread metrics for a given level."""
        buy_price = buy_result.weighted_price
        sell_price = sell_result.weighted_price

        # Calculate spread
        absolute_spread = buy_price - sell_price if buy_price > 0 and sell_price > 0 else Decimal('0')

        mid_price = (buy_price + sell_price) / Decimal('2')
        relative_spread = (absolute_spread / mid_price) * Decimal('100') if mid_price > 0 else Decimal('0')

        # Calculate market impact
        market_impact_buy = ((buy_price - best_ask) / best_ask) * Decimal('100') if best_ask > 0 else Decimal('0')
        market_impact_sell = ((best_bid - sell_price) / best_bid) * Decimal('100') if best_bid > 0 else Decimal('0')

        return SpreadAnalysis(
            level_quote=self._round_decimal(level),
            buy_price=self._round_decimal(buy_price, 2),
            sell_price=self._round_decimal(sell_price, 2),
            buy_filled_quote=self._round_decimal(buy_result.actual_amount_filled, 2),
            sell_filled_quote=self._round_decimal(sell_result.actual_amount_filled, 2),
            absolute_spread=self._round_decimal(absolute_spread, 2),
            relative_spread_pct=self._round_decimal(relative_spread, 4),
            market_impact_buy_pct=self._round_decimal(market_impact_buy, 4),
            market_impact_sell_pct=self._round_decimal(market_impact_sell, 4)
        )

    def _create_market_summary(
            self,
            market_orderbook: Dict,
            best_bid: Decimal,
            best_ask: Decimal
    ) -> MarketSummary:
        """Create market summary from orderbook data."""
        best_spread = best_ask - best_bid
        mid_price = (best_ask + best_bid) / Decimal('2')
        best_spread_pct = (best_spread / mid_price) * Decimal('100') if mid_price > 0 else Decimal('0')

        return MarketSummary(
            best_bid=self._round_decimal(best_bid, 2),
            best_ask=self._round_decimal(best_ask, 2),
            best_spread=self._round_decimal(best_spread, 2),
            best_spread_pct=self._round_decimal(best_spread_pct, 4),
            market_id=market_orderbook.get('marketId', 'Unknown'),
        )

    def _round_decimal(self, value: Decimal, places: int = None) -> Decimal:
        """Round decimal to specified places or default precision."""
        if places is None:
            places = self.precision
        quantize_exp = Decimal('0.1') ** places
        return value.quantize(quantize_exp, rounding=ROUND_HALF_UP)


# Convenience functions for backward compatibility
def get_weighted_price(orders: List[List[str]], target_amount: float) -> Tuple[float, float]:
    """
    Legacy function for backward compatibility.

    Args:
        orders: List of [price, quantity] pairs
        target_amount: Target amount

    Returns:
        Tuple of (weighted_price, actual_amount_filled)
    """
    analyzer = OrderbookAnalyzer()
    result = analyzer.get_weighted_price(orders, Decimal(str(target_amount)))
    return float(result.weighted_price), float(result.actual_amount_filled)


def calculate_spreads(market_orderbook: Dict, levels: List[float]) -> Dict[str, Dict]:
    """
    Legacy function for backward compatibility.

    Args:
        market_orderbook: Dictionary containing 'asks' and 'bids' data
        levels: List of amounts to calculate spreads for

    Returns:
        Dictionary with spread analysis for each level
    """
    analyzer = OrderbookAnalyzer()
    return analyzer.calculate_spreads(market_orderbook, levels)

