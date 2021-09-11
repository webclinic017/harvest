# Builtins
import re
import threading
import sys
from sys import exit
from signal import signal, SIGINT
import time
import logging

# External libraries

# Submodule imports
from harvest.utils import *
from harvest.storage import BaseStorage
from harvest.api.yahoo import YahooStreamer
from harvest.api.dummy import DummyStreamer
from harvest.api.paper import PaperBroker
from harvest.algo import BaseAlgo
from harvest.storage import BaseStorage
from harvest.storage import BaseLogger
from harvest.server import Server

class Trader:
    """
    :watch: Watchlist containing all stock and cryptos to monitor.
        The user may or may not own them. Note it does NOT contain options. 
    :broker: Both the broker and streamer store a Broker object.
        Broker places orders and retrieves latest account info like equity.
    :streamer: Streamer retrieves the latest stock price and calls handler().
    """

    interval_list = ['1MIN', '5MIN', '15MIN', '30MIN', '1HR', '1DAY']

    def __init__(self, streamer=None, broker=None, storage=None, debug=False):
        """Initializes the Trader. 
        """

        signal(SIGINT, self.exit)

        # Harvest only supports Python 3.8 or newer.
        if sys.version_info[0] < 3 or sys.version_info[1] < 8:
            raise Exception("Harvest requires Python 3.8 or above.")

        # If streamer is not specified, use YahooStreamer
        self.streamer = YahooStreamer() if streamer is None else streamer
        # If broker is not specified and streamer is YahooStreamer, use PaperBroker
        if broker is None:
            if isinstance(self.streamer, (YahooStreamer, DummyStreamer)):
                self.broker = PaperBroker()
            else:
                self.broker = self.streamer
        else:
            self.broker = broker

        # Initialize timestamp
        self.timestamp_prev = now()
        self.timestamp = self.timestamp_prev

        self.watchlist = []         # List of securities specified in this class.
        self.watchlist_all = []     # List of securities specified in this class, 
                                    # fetched from brokers, and retrieved from Algo class.

        self.account = {}           # Local cache of account data.

        self.stock_positions = []   # Local cache of current stock positions.
        self.option_positions = []  # Local cache of current options positions.
        self.crypto_positions = []  # Local cache of current crypto positions.

        self.order_queue = []       # Queue of unfilled orders.

        # Initialize the storage
        self.storage = BaseStorage() if storage is None else storage

        self.logger = BaseLogger()

        self.block_lock = threading.Lock() # Lock for streams that receive data asynchronously.

        self.algo = []  # List of algorithms to run.

        # Initialize the web interface server
        self.server = Server(self)

        self.debugger = logging.getLogger("harvest")
        self.debugger.setLevel("DEBUG")
        if debug:
            f_handler = logging.FileHandler("trader.log")
            f_handler.setLevel(logging.DEBUG)
            f_format = logging.Formatter('%(asctime)s : %(name)s : %(levelname)s : %(message)s')
            f_handler.setFormatter(f_format)
            self.debugger.addHandler(f_handler)

        c_handler = logging.StreamHandler()
        if debug:
            c_handler.setLevel(logging.DEBUG)
        else:
            c_handler.setLevel(logging.INFO)
        c_format = logging.Formatter('%(asctime)s : %(name)s : %(levelname)s : %(message)s')
        c_handler.setFormatter(c_format)
        self.debugger.addHandler(c_handler)

    def storage_init(self):
        """Initializes the storage.
        """
        for s in self.watchlist_all:
            for i in [self.fetch_interval] + self.aggregations:
                df = self.streamer.fetch_price_history(s, i)
                self.storage.store(s, i, df)

    def _setup_account(self):
        """Initializes local cache of account info. 
        For testing, it should manually be specified
        """
        ret = self.broker.fetch_account()
        self.account = ret
    
    def _setup_stats(self):
        """Initializes local cache of stocks, options, and crypto positions.
        """
        
        # Get any pending orders 
        ret = self.broker.fetch_order_queue()
        self.order_queue = ret
        self.debugger.debug(f"Fetched orders:\n{self.order_queue}")

        # Get positions
        pos = self.broker.fetch_stock_positions()
        self.stock_positions = pos
        pos = self.broker.fetch_option_positions()
        self.option_positions = pos
        pos = self.broker.fetch_crypto_positions()
        self.crypto_positions = pos
        self.debugger.debug(f"Fetched positions:\n{self.stock_positions}\n{self.option_positions}\n{self.crypto_positions}")

        # Update option stats
        self.broker.update_option_positions(self.option_positions)
        self.debugger.debug(f"Updated option positions:\n{self.option_positions}")

    def start(self, interval='5MIN', aggregations=[], sync=True, kill_switch: bool=False, server=False):
        """Entry point to start the system. 
        
        :param str? interval: The interval to run the algorithm. defaults to '5MIN'
        :param list[str]? aggregations: A list of intervals. The Trader will aggregate data to the intervals specified in this list.
            For example, if this is set to ['5MIN', '30MIN'], and interval is '1MIN', the algorithm will have access to 
            5MIN, 30MIN aggregated data in addition to 1MIN data. defaults to None
        :param bool? sync: If true, the system will sync with the broker and fetch current positions and pending orders. defaults to true. 
        :kill_switch: If true, kills the infinite loop in streamer. Primarily used for testing. defaults to False.

        """
        self.debugger.debug(f"Setting up Harvest...")

        if len(self.algo) == 0:
            raise Exception(f"No algorithm specified.")

        self.aggregations = aggregations
        self.interval = interval
        self.watchlist_all = self.watchlist.copy()

        min_interval = '1DAY'
        for a in self.algo:
            a.config()

            if a.interval is None:
                a.interval = interval 
            if self.interval_list.index(a.interval) < self.interval_list.index(min_interval):
                self.aggregations.append(min_interval)
                min_interval = a.interval
            
            if a.aggregations is None:
                a.aggregations = []
                for agg in aggregations:
                    if self.interval_list.index(a.interval) < self.interval_list.index(agg):
                        a.aggregations.append(agg)
            else:
                self.aggregations.append(a.aggregations)

            if a.watchlist is None:
                a.watchlist = self.watchlist
            else:
                self.watchlist_all.append(a.watchlist)
        
        self.interval = min_interval

        # Initialize the account
        self._setup_account()

        # If sync is on, call the broker to load pending orders and all positions currently held.
        if sync:
            self._setup_stats()
            for s in self.stock_positions:
                self.watchlist_all.append(s['symbol'])
            for s in self.option_positions:
                self.watchlist_all.append(s['symbol'])
            for s in self.crypto_positions:
                self.watchlist_all.append(s['symbol'])
            for s in self.order_queue:
                self.watchlist_all.append(s['symbol'])     

        if len(self.watchlist_all) == 0:
            raise Exception(f"No securities were added to watchlist")

        # Remove duplicates in watchlist
        self.watchlist_all = list(set(self.watchlist_all))
        self.debugger.debug(f"Watchlist: {self.watchlist_all}")

        if not self.streamer.has_interval(self.interval):
            raise Exception(f"""Interval '{self.interval}' is not supported by the selected streamer.\n 
                                The streamer only supports {self.streamer.interval_list}""")

        self.broker.setup(self.watchlist_all, self.interval, self, self.main)
        self.streamer.setup(self.watchlist_all, self.interval, self, self.main)

        self.fetch_interval = self.streamer.fetch_interval
        self.debugger.debug(f"Interval: {interval}\nFetch interval: {self.fetch_interval}")

        if self.interval != self.fetch_interval:
            self.aggregations.append(self.interval)
        self.aggregations = list(set(self.aggregations))
        self.debugger.debug(f"Aggregations: {self.aggregations}")
        
        self.storage_init()

        for a in self.algo:
            a.setup()

        self.debugger.debug("Setup complete")

        self.blocker = {}
        for w in self.watchlist_all:
            self.blocker[w] = False
        self.block_queue = {}
        self.needed = self.watch.copy()

        if server:
            self.server.start()

        self.streamer.start(kill_switch)

    def timeout(self):
        self.debugger.debug("Begin timeout timer")
        time.sleep(1)
        if not self.all_recv:
            self.debugger.debug("Force flush")
            self.flush()

    def main(self, df_dict):

        self.debugger.debug(f"Received: \n{df_dict}")

        if len(self.needed) == len(self.watch):
            self.timestamp_prev = self.timestamp
            self.timestamp = now()
            first = True

        symbols = [k for k, v in df_dict.items()]
        self.debugger.debug(f"Got data for: {symbols}")
        self.needed = list(set(self.needed) - set(symbols))
        self.debugger.debug(f"Still need data for: {self.needed}")
 
        self.block_queue.update(df_dict)
        self.debugger.debug(self.block_queue)
        
        # If all data has been received, pass on the data
        if len(self.needed) == 0:
            self.debugger.debug("All data received")
            self.needed = self.watch.copy()
            self.main_helper(self.block_queue)
            self.block_queue = {}
            self.needed = self.watch.copy()
            self.all_recv = True
            return 
        
        # If there are data that has not been received, 
        # start a timer 
        if first:
            timer = threading.Thread(target=self.timeout, daemon=True)
            timer.start()
            self.all_recv = False
        
        
    def flush(self):
        # For missing data, repeat the existing one
        got  = list(set(self.watch) - set(self.needed))[0]
        timestamp = self.block_queue[got].index[-1]
        for n in self.needed:
            data = self.storage.load(n, self.fetch_interval).iloc[[-1]].copy()
            data.index = [timestamp]
            self.block_queue[n] = data
        self.needed = self.watch.copy()
        self.main_helper(self.block_queue)
        self.block_queue = {}
        return

    def main_helper(self, df_dict):

        new_day = self.timestamp.date() > self.timestamp_prev.date()
        
        # Periodically refresh access tokens
        if self.timestamp.hour % 12 == 0 and self.timestamp.minute == 0:
            self.streamer.refresh_cred()
        
        # Save the data locally
        for s in self.watch:
            self.storage.store(s, self.fetch_interval, df_dict[s])
        
        # Aggregate the data to other intervals
        for s in self.watch:
            for i in self.aggregations:
                self.storage.aggregate(s, self.fetch_interval, i)

        # If an order was processed, fetch the latest position info.
        # Otherwise, calculate current positions locally
        update = self._update_order_queue()
        self._update_stats(df_dict, new=update, option_update=True)

        new_algo = []
        for a in self.algo:
            if not self.is_freq(self.timestamp, a.interval):
                new_algo.append(a)
                continue
            try:
                a.main()
                new_algo.append(a)
            except Exception as e:
                self.debugging.warning(f"Algorithm {a} failed, removing from algorithm list.\nException: {e}")
        self.algo = new_algo

        self.broker.exit()
        self.streamer.exit()

    def is_freq(self, time, interval):
        """Helper function to determine if algorithm should be invoked for the
        current timestamp. For example, if interval is 30MIN,
        algorithm should be called when minutes are 0 and 30.
        """
        time = time.astimezone(pytz.timezone('UTC'))
       
        if interval == '1MIN':
            return True 

        minutes = time.minute
        hours = time.hour
        if interval == '1DAY':
            # TODO: Use API to get real-time market hours
            return minutes == 50 and hours == 19
        elif interval == '1HR':
            return minutes == 0
        val = int(re.sub("[^0-9]", "", self.interval))
        return minutes % val == 0

    def _update_order_queue(self):
        """Check to see if outstanding orders have been accepted or rejected
        and update the order queue accordingly.
        """
        self.debugger.debug(f"Updating order queue: {self.order_queue}")
        for i, order in enumerate(self.order_queue):
            if 'type' not in order:
                raise Exception(f"key error in {order}\nof {self.order_queue}")
            if order['type'] == 'STOCK':
                stat = self.broker.fetch_stock_order_status(order["id"])
            elif order['type'] == 'OPTION':
                stat = self.broker.fetch_option_order_status(order["id"])
            elif order['type'] == 'CRYPTO':
                stat = self.broker.fetch_crypto_order_status(order["id"])
            self.debugger.debug(f"Updating status of order {order['id']}")
            self.order_queue[i] = stat

        self.debugger.debug(f"Updated order queue: {self.order_queue}")
        new_order = []
        order_filled = False
        for order in self.order_queue:
            if order['status'] == 'filled':
                order_filled = True  
            else:
                new_order.append(order)
        self.order_queue = new_order

        # if an order was processed, update the positions and account info
        return order_filled
           
    def _update_stats(self, df_dict, new=False, option_update=False):
        """Update local cache of stocks, options, and crypto positions
        """
        # Update entries in local cache
        # API should also be called if load_watch is false, as there is a high chance 
        # that data in local cache are not representative of the entire portfolio,
        # meaning total equity cannot be calculated locally
        if new:
            pos = self.broker.fetch_stock_positions()
            self.stock_positions = [p for p in pos if p['symbol'] in self.watch]
            pos = self.broker.fetch_option_positions()
            self.option_positions = [p for p in pos if p['symbol'] in self.watch]
            pos = self.broker.fetch_crypto_positions()
            self.crypto_positions = [p for p in pos if p['symbol'] in self.watch]
            ret = self.broker.fetch_account()
            self.account = ret

        if option_update:
            self.broker.update_option_positions(self.option_positions)
        
        self.debugger.debug(f"Stock positions: {self.stock_positions}")
        self.debugger.debug(f"Option positions: {self.option_positions}")
        self.debugger.debug(f"Crypto positions: {self.crypto_positions}")

        if new:
            return 
     
        net_value = 0
        for p in self.stock_positions + self.crypto_positions:
            key = p['symbol']
            price = df_dict[key][key]['close'][0]
            p['current_price'] = price 
            value = price * p['quantity']
            p['market_value'] = value
            net_value = net_value + value
        
        equity = net_value + self.account['cash']
        self.account['equity'] = equity

    def fetch_chain_info(self, *args, **kwargs):
        return self.streamer.fetch_chain_info(*args, **kwargs)
    
    def fetch_chain_data(self, *args, **kwargs):
        return self.streamer.fetch_chain_data(*args, **kwargs)
    
    def fetch_option_market_data(self, *args, **kwargs):
        return self.streamer.fetch_option_market_data(*args, **kwargs)

    def buy(self, symbol: str, quantity: int, in_force: str, extended: bool):
        ret = self.broker.buy(symbol, quantity, in_force, extended)
        if ret == None:
            self.debugger.debug("BUY failed")
            return None
        self.order_queue.append(ret)
        self.debugger.debug(f"BUY: {self.timestamp}, {symbol}, {quantity}")
        self.debugger.debug(f"BUY order queue: {self.order_queue}")
        asset_type = 'crypto' if is_crypto(symbol) else 'stock'
        self.logger.add_transaction(self.timestamp, 'buy', asset_type, symbol, quantity)
        return ret

    def sell(self, symbol: str, quantity: int, in_force: str, extended: bool):
        ret = self.broker.sell(symbol, quantity, in_force, extended)
        if ret == None:
            self.debugger.debug("SELL failed")
            return None
        self.order_queue.append(ret)
        self.debugger.debug(f"SELL: {self.timestamp}, {symbol}, {quantity}")
        self.debugger.debug(f"SELL order queue: {self.order_queue}")
        asset_type = 'crypto' if is_crypto(symbol) else 'stock'
        self.logger.add_transaction(self.timestamp, 'sell', asset_type, symbol, quantity)
        return ret


    def buy_option(self, symbol: str, quantity: int, in_force: str):
        ret = self.broker.buy_option(symbol, quantity, in_force)
        if ret == None:
            raise Exception("BUY failed")
        self.order_queue.append(ret)
        self.debugger.debug(f"BUY: {self.timestamp}, {symbol}, {quantity}")
        self.debugger.debug(f"BUY order queue: {self.order_queue}")
        self.logger.add_transaction(self.timestamp, 'buy', 'option', symbol, quantity)
        return ret

    def sell_option(self, symbol: str, quantity: int, in_force: str):
        ret = self.broker.sell_option(symbol, quantity, in_force)
        if ret == None:
            raise Exception("SELL failed")
        self.order_queue.append(ret)
        self.debugger.debug(f"SELL: {self.timestamp}, {symbol}, {quantity}")
        self.debugger.debug(f"SELL order queue: {self.order_queue}")
        self.logger.add_transaction(self.timestamp, 'sell', 'option', symbol, quantity)
        return ret
    
    def set_algo(self, algo):
        """Specifies the algorithm to use.

        :param Algo algo: The algorithm to use. You can either pass in a single Algo class, or a 
            list of Algo classes. 
        """
        if isinstance(algo, list):
            self.algo = algo
        else:
            self.algo = [algo]
    
    def set_symbol(self, symbol):
        """Specifies the symbol(s) to watch.
        
        Cryptocurrencies should be prepended with an `@` to differentiate them from stocks. 
        For example, '@ETH' will refer to Etherium, while 'ETH' will refer to Ethan Allen Interiors. 
        If this method was previously called, the symbols specified earlier will be replaced with the
        new symbols.
        
        :symbol str symbol: Ticker Symbol(s) of stock or cryptocurrency to watch. 
            It can either be a string, or a list of strings. 
        """
        if isinstance(symbol, list):
            self.watchlist = symbol
        else:
            self.watchlist = [symbol]
    
    def exit(self, signum, frame):
        # TODO: Gracefully exit
        self.debugger.debug("\nStopping Harvest...")
        exit(0)
    
    