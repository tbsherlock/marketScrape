import unittest
from decimal import Decimal

from src.scraper.binance_api import BinanceClient
from src.scraper.btcm_api import BTCMarketsClient
from src.scraper.orderbook_logic import calculate_spreads

class TestMyCalculator(unittest.TestCase):
    def setUp(self):
        self.btcm_api = BTCMarketsClient()
        self.binance_api = BinanceClient()

    def test_btcm_get_active_markets(self):
        active_markets = self.btcm_api.get_active_markets()
        print(f"active_markets: {active_markets}")

    def test_btcm_get_market_orderbook(self):
        market_orderbook = self.btcm_api.get_market_orderbook("XRP-AUD")
        print(f"test_get_market_orderbook: {market_orderbook}")

    def test_bina_exchange_information(self):
        pass  # slow request
        #exchange_information = self.binance_api.exchange_information()
        #print(f"test_get_market_orderbook: {exchange_information}")

    def test_bina_current_average_price(self):
        # symbols examples, 'AVAXUSDT', 'ETHUSDT', 'AUDUSDT', 'XRPUSDT'
        current_average_price = self.binance_api.current_average_price('XRPUSDT')
        print(f"current_average_price: {current_average_price}")

    def test_market_orderbook(self):
        test_market_orderbook = {
            'marketId':'ETH-AUD',
            'snapshotId':1757819116258000,
            'asks':[['7039.31', '2.57690088'], ['7040.04', '0.2491'], ['7043.3', '8.143697'], ['7043.55', '0.2491'],
                    ['7049.97', '0.852'], ['7049.98', '0.02'], ['7050', '1'], ['7050', '2'], ['7059.24', '0.448976'],
                    ['7070.7', '4.9109'], ['7070.87', '3.2'], ['7074.73', '0.56697'], ['7076.02', '1.799204'],
                    ['7079.94', '0.90288'], ['7099.98', '0.02'], ['7100', '0.07'], ['7102.37', '0.864204'],
                    ['7110.38', '0.427284'], ['7125', '11'], ['7135', '0.3'], ['7135', '0.2'], ['7139.98', '0.02'],
                    ['7139.98', '0.02'], ['7148.51', '1'], ['7149.98', '0.02'], ['7150', '0.25'], ['7150', '0.75'],
                    ['7164.51', '0.442464'], ['7199.98', '0.01'], ['7200', '1'], ['7200', '1'], ['7200', '5'],
                    ['7200', '0.14'], ['7200', '0.2'], ['7200', '5'], ['7200', '12.8'], ['7200', '1'], ['7200', '2.8'],
                    ['7200', '1.5'], ['7212', '0.2'], ['7212', '1.2'], ['7250', '2'], ['7250', '1'], ['7250', '0.5'],
                    ['7250', '1'], ['7275', '0.1325'], ['7280', '1'], ['7299.98', '0.01'], ['7300', '0.5'],
                    ['7310', '0.2']],
            'bids':[['7024.21', '2'], ['7024.2', '5.909882'], ['7023.88', '3.336'], ['7020.42', '0.438944'],
                    ['7020.14', '4.27341904'], ['7020.12', '0.2491'], ['7018.53', '0.77875051'], ['7016.22', '0.2491'],
                    ['7014.44', '0.876876'], ['7007.27', '0.853'], ['7006.43', '1.732588'], ['7004.7', '3.2'],
                    ['6990.17', '0.877228'], ['6937.95', '0.450076'], ['6930', '0.64'], ['6900', '0.005'],
                    ['6883.96', '0.430056'], ['6864', '0.2'], ['6820', '0.8'], ['6800', '1.5'],
                    ['6777.77', '0.06004903'], ['6770.88', '0.57'], ['6749', '0.2'], ['6678', '0.2'],
                    ['6641', '0.06019358'], ['6582', '0.1'], ['6580', '0.15'], ['6525', '0.08'], ['6520', '0.5'],
                    ['6510.01', '0.113987'], ['6510', '3'], ['6510', '5.5954'], ['6501', '5'], ['6500', '0.03'],
                    ['6500', '0.5'], ['6500', '0.65'], ['6493.84', '0.38807102'], ['6490', '1.63942014'], ['6475', '1'],
                    ['6452', '0.00000026'], ['6450', '0.5'], ['6450', '1'], ['6400', '0.2'], ['6400', '0.25'],
                    ['6400', '3.11135262'], ['6395', '0.05'], ['6388', '0.15537934'], ['6388', '0.018'],
                    ['6349.19', '0.05130295'], ['6340', '1']]
        }

        # Calculate spreads at the requested levels
        levels = [100, 1000, 10000, 100000]
        results = calculate_spreads(test_market_orderbook, levels)
        print("test_market_orderbook: ", results)
        bars = [float(results['100_QUOTE']['absolute_spread']), float(results['100_QUOTE']['buy_price']), float(results['100_QUOTE']['sell_price'])]
        print("bars:", bars)

    def test_market_orderbook_2(self):
        # Test data
        TEST_MARKET_ORDERBOOK = {
            'marketId':'BASE-QUOTE',
            'snapshotId':1757819116258000,
            'asks':[['7039.31', '2.57690088'], ['7040.04', '0.2491'], ['7043.3', '8.143697'],
                    ['7043.55', '0.2491'], ['7049.97', '0.852'], ['7049.98', '0.02'],
                    ['7050', '1'], ['7050', '2'], ['7059.24', '0.448976']],
            'bids':[['7024.21', '2'], ['7024.2', '5.909882'], ['7023.88', '3.336'],
                    ['7020.42', '0.438944'], ['7020.14', '4.27341904'], ['7020.12', '0.2491'],
                    ['7018.53', '0.77875051'], ['7016.22', '0.2491']]
        }


if __name__ == '__main__':
    unittest.main()

