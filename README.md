![Header](docs/banner.png)

[![codecov](https://codecov.io/gh/tfukaza/harvest/branch/main/graph/badge.svg?token=NQMXTBK2UO)](https://codecov.io/gh/tfukaza/harvest)
![run tests](https://github.com/tfukaza/harvest/actions/workflows/run-tests.yml/badge.svg)
![website](https://github.com/tfukaza/harvest/actions/workflows/build-website.yml/badge.svg)



**⚠️WARNING⚠️**
Harvest is currently at **v0.0**, meaning the code is generally unstable. Use with caution. 
- Found a bug? We'll love it if you can take your time to [file a bug report](https://github.com/tfukaza/harvest/issues/new?assignees=&labels=bug&template=bug_report.md&title=%5B%F0%9F%AA%B0BUG%5D), so we can start fixing it. 
- Have ideas to improve or add a feature? [Submit a feature suggestion](https://github.com/tfukaza/harvest/issues/new?assignees=&labels=enhancement%2C+question&template=feature-request.md&title=%5B%F0%9F%92%A1Feature+Request%5D)!
- Can't find the info you need? [Request documentation](https://github.com/tfukaza/harvest/issues/new?assignees=&labels=documentation&template=documentation.md&title=%5B%F0%9F%93%9DDocumentation%5D)

## What is Harvest?
Harvest is a Python based framework for algorithmic trading. It provides a simple and intuitive interface to 
Visit Harvest's [**website**](https://tfukaza.github.io/harvest/) for more details.

## Example
Below is minimal example of a crossover strategy for `TWTR` implemented with Harvest
```python
from harvest.algo import BaseAlgo
from harvest.trader import Trader
from harvest.broker.robinhood import RobinhoodBroker

class Watch(BaseAlgo):
    def main(self, _):
        sma_long = self.sma(period=50)
        sma_short = self.sma(period=20)
        if self.crossover(sma_long, sma_short):
            self.buy()
        elif self.crossover(sma_short, sma_long):
            self.sell()

if __name__ == "__main__":
    t = Trader( RobinhoodBroker() )
    t.set_symbol('TWTR')
    t.set_algo(Watch())
    t.start()
```

## Installation
The only prerequisite is to have **Python version 3.8 or greater**.

Harvest is still early in development, so you'll have to install it directly from this repo. 
```bash
pip install -e git+https://github.com/tfukaza/harvest.git
```
Next, install the dependencies necessary for the brokerage of your choice. Currently, Harvest only supports Robinhood. 
```bash
pip install -e 'git+https://github.com/tfukaza/harvest.git#egg=harvest[Robinhood]'
```
Now you're all set!

## Disclaimer
Harvest is an open-source passion project created by algo trading enthusiasts. 
- It is not officially associated with Robinhood LLC.  
- Tutorials and documentation solely exist to provide technical references of the code. They are not recommendations of any specific securities or strategies. 
- Use Harvest at your own responsibility. 
