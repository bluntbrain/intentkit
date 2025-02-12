"""Tool for fetching trading signals via CryptoCompare API."""

from typing import Any, Dict, Type
from pydantic import BaseModel
from skills.cryptocompare.base import CryptoCompareBaseTool
from skills.cryptocompare.api import fetch_trading_signals, FetchTradingSignalsInput

class CryptoCompareFetchTradingSignalsOutput(BaseModel):
    result: Dict[str, Any]
    error: str | None = None

class CryptoCompareFetchTradingSignals(CryptoCompareBaseTool):
    name: str = "cryptocompare_fetch_trading_signals"
    description: str = FETCH_TRADING_SIGNALS_PROMPT
    args_schema: Type[BaseModel] = FetchTradingSignalsInput

    def _run(self) -> CryptoCompareFetchTradingSignalsOutput:
        raise NotImplementedError("Use _arun instead")

    async def _arun(self) -> CryptoCompareFetchTradingSignalsOutput:
        input_data: FetchTradingSignalsInput = self.args
        is_rate_limited, error_msg = await self.check_rate_limit()
        if is_rate_limited:
            return CryptoCompareFetchTradingSignalsOutput(result={}, error=error_msg)
        try:
            result = await fetch_trading_signals(input_data.from_symbol)
            return CryptoCompareFetchTradingSignalsOutput(result=result)
        except Exception as e:
            return CryptoCompareFetchTradingSignalsOutput(result={}, error=str(e))

FETCH_TRADING_SIGNALS_PROMPT = """
This tool retrieves advanced trading signals from IntoTheBlock analytics for a specific cryptocurrency.
Provide a cryptocurrency symbol (e.g., 'BTC') to get detailed market indicators.
Returns key metrics like network growth, large transaction patterns, holder composition, and market momentum.
"""


