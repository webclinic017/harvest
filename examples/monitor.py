"""
This code monitors a given stock/crypto symbol.
"""
from harvest.algo import BaseAlgo
from harvest.trader import Trader
from harvest.broker.robinhood import RobinhoodBroker

class Watch(BaseAlgo):
    def main(self, meta):
        print( self.get_price() )

if __name__ == "__main__":
    t = Trader( RobinhoodBroker() )
    t.set_symbol('@BTC')
    t.set_algo(Watch())

    t.start('1MIN')