import requests
import json
from bscscan import BscScan
import asyncio
import time
from dotenv import load_dotenv
import os
import logging

"""Setup logger"""
logging.basicConfig(filename='stats.log', level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s %(name)s %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

COVALENT_KEY = os.getenv('COVALENT_KEY')
BITQUERY_KEY = os.getenv('BITQUERY_KEY')
BSCSCAN_KEY = os.getenv('BSCSCAN_KEY')


def run_covalent(contract_address, yesterday_block, now_block):
    """
    Basic function to get holders amount from covalent.
    """
    request = requests.get(f'https://api.covalenthq.com/v1/56/tokens/{contract_address}/token_holders_changes/?quote-currency=USD&format=JSON&starting-block={yesterday_block}&ending-block={now_block}&key={COVALENT_KEY}')
    return request.json()


def run_covalent_yesterday_holder(contract_address, yesterday_block):
    """
    Basic functions to get yesterday holders amount from covalent.
    """
    request = requests.get(f'https://api.covalenthq.com/v1/56/tokens/{contract_address}/token_holders_changes/?quote-currency=USD&format=JSON&starting-block={yesterday_block}&ending-block={yesterday_block}&key={COVALENT_KEY}')
    return request.json()


def run_query(query):
    """
    Basic function to get info from bitquery.
    """
    headers = {'X-API-KEY': f'{BITQUERY_KEY}'}
    request = requests.post('https://graphql.bitquery.io/',
                            json={'query': query}, headers=headers)
    if request.status_code == 200:
        return request.json()
    else:
        raise Exception('Query failed and return code is {}.      {}'.format(request.status_code,
                        query))


class Token:

    def __init__(self, address, marketing_wallet, rewards_contract, rewarded_token_contract_address, burn_address, lp_address):
        self.now = time.time()
        self.address = address
        self.marketing_wallet_address = marketing_wallet
        self.rewards_contract_address = rewards_contract
        self.rewarded_token_contract_address = rewarded_token_contract_address
        self.burn_address = burn_address
        self.lp_address = lp_address
        self.holders = 0
        self.yesterday_holders = 0
        self.transactions = 0
        self.marketing_wallet_value_usd = 0
        self.distributed_rewards = 0
        self.circulating_supply = 0
        self.decimal = 0
        self.holders_lst = []
        self.bnb_price = 0
        self.market_cap = 0
        self.block_now = 0
        self.yesterday_block = 0
        self.one_p_amount = 0
        self.percent_owned_by_10 = 0

    async def get_circulation_supply(self):
        """
        Function calculate circulating supply.
        """
        async with BscScan(BSCSCAN_KEY) as client:
            self.block_now = await client.get_block_number_by_timestamp(
                timestamp=f"{int(self.now)}",
                closest="before")
            self.yesterday_block = await client.get_block_number_by_timestamp(
                timestamp=f"{int(self.now - 86400)}",
                closest="before")

        async with BscScan(BSCSCAN_KEY) as client:
            bnb_price = await client.get_bnb_last_price()
        self.bnb_price = float(bnb_price['ethusd'])

        async with BscScan(BSCSCAN_KEY) as client:
            total_supply = await client.get_total_supply_by_contract_address(
                    contract_address=f"{self.address}"
                )
        async with BscScan(BSCSCAN_KEY) as client:
            decimal = await client.get_bep20_token_transfer_events_by_contract_address_paginated(
                    contract_address=f"{self.address}",
                    page=1,
                    offset=1,
                    sort="asc"
                )
        self.decimal = decimal[0]['tokenDecimal']
        try:
            async with BscScan('UEIRQK6Y6Y2GCVUMRI763UE28VEG92UDHU') as client:
                burn_address_balance = await client.get_acc_balance_by_token_contract_address(
                    contract_address=f"{self.address}",
                    address=f"{self.burn_address}")
        except:
            print('no burn address')
        self.circulating_supply = int((float(total_supply) - float(burn_address_balance)) / 10 ** int(self.decimal))

    def get_lp_info(self):
        """
        Function calculate market capitalization. Works only if in LP more tokens than wbnb
        """
        query = """query{
            ethereum(network: bsc) {
            address(address: { is: "%s"}) {
            balances(
                currency: { in: ["%s",
                                 "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"]}
        ) {value}
        }}}""" % (self.lp_address, self.address)
        res = run_query(query)
        if float(res['data']['ethereum']['address'][0]['balances'][0]['value']) > float(res['data']['ethereum']['address'][0]['balances'][1]['value']):
            token_amount = float(res['data']['ethereum']['address'][0]['balances'][0]['value'])
            wbnb_amount = float(res['data']['ethereum']['address'][0]['balances'][1]['value'])
        else:
            token_amount = float(res['data']['ethereum']['address'][0]['balances'][1]['value'])
            wbnb_amount = float(res['data']['ethereum']['address'][0]['balances'][0]['value'])
        self.market_cap = round(self.circulating_supply * (wbnb_amount / token_amount) * self.bnb_price, 2)

    def get_transactions_number(self):
        """
        Function update amount of transaction.
        """
        query = """query unique_transfers {
            ethereum(network: bsc) {
            transfers(currency: { is: "%s"}) {
            count(uniq: transfers)}}}""" % (self.address)
        res = run_query(query)
        self.transactions = res['data']['ethereum']['transfers'][0]['count']

    def get_marketing_wallet_value(self):
        """
        Function update value of marketing wallet.
        """
        query = """query marketing_wallet {
        ethereum(network: bsc) {
        coinpath(
        receiver: {is: "%s"}
        sender: {is: "%s"}
        ) {
      amount(in: USD)}}}""" % (self.marketing_wallet_address, self.address)
        res = run_query(query)
        self.marketing_wallet_value_usd = round(res['data']['ethereum']['coinpath'][0]['amount'], 2)

    def get_holders_number(self):
        """
        Function update amount of holders and create list of holders for further analysis.
        """
        self.yesterday_holders = run_covalent_yesterday_holder(self.address, self.yesterday_block)['data']['pagination']['total_count']
        holders = run_covalent(self.address, self.yesterday_block, self.block_now)
        self.holders = holders['data']['pagination']['total_count']
        for x in holders['data']['items']:
            if x['token_holder'] != self.burn_address and x['token_holder'] != self.lp_address:
                self.holders_lst.append(int(x['next_balance']) / (10 ** int(self.decimal)))

    def get_distributed_rewards(self):
        """
        Function update amount of distributed rewards.
        """
        query = """
        query {
        ethereum(network: bsc) {
        transfers(
          currency: {is: "%s"}
          sender: {is: "%s"}){
          amount(calculate: sum)}}}""" % (self.rewarded_token_contract_address, self.rewards_contract_address)
        result = run_query(query)
        self.distributed_rewards = result['data']['ethereum']['transfers'][0]['amount']

    def holders_analysis(self):
        """
        Additional function that calculate .
        """
        one_p = [x for x in self.holders_lst if x >= self.circulating_supply / 100]
        one_p_amount = len(one_p)
        percent_owned_by_10 = (sum(self.holders_lst[:10]) / self.circulating_supply) * 100
        self.one_p_amount = one_p_amount
        self.percent_owned_by_10 = percent_owned_by_10

    def to_file(self):
        """
        Saves results to json file.
        """
        data = {'address': self.address,
                'holders': self.holders,
                '24h holders change': self.holders - self.yesterday_holders,
                'transactions': self.transactions,
                'marketing wallet USD': self.marketing_wallet_value_usd,
                'distributed rewards': self.distributed_rewards,
                'circulating supply': self.circulating_supply,
                'market cap': self.market_cap,
                'percent owned by first 10 wallets': self.percent_owned_by_10,
                'number of holder owned at least 1 percent': self.one_p_amount}

        with open(f'{self.address}.json', 'w') as f:
            json.dump(data, f, indent=0)

    def synchronize_data(self):
        """
        Runs all other functions and print in console and log to file if something goes wrong.
        """
        try:
            asyncio.run(self.get_circulation_supply())
        except AssertionError as error:
            print(error)
        except Exception as e:
            logger.error(e)
            print('get_circulation_supply failed!')
        try:
            self.get_lp_info()
        except Exception as e:
            logger.error(e)
            print('get_lp_info failed!')
        try:
            self.get_transactions_number()
        except Exception as e:
            logger.error(e)
            print('get_transactions_number failed!')
        try:
            self.get_holders_number()
        except Exception as e:
            logger.error(e)
            print('get_holders_number failed!')
        try :
            self.get_distributed_rewards()
        except Exception as e:
            logger.error(e)
            print('get_distributed_rewards failed!')
        try:
            self.get_marketing_wallet_value()
        except Exception as e:
            logger.error(e)
            print('get_marketing_wallet_value failed!')
        try:
            self.holders_analysis()
        except Exception as e:
            logger.error(e)
            print('holder_analysis failed!')
        try:
            self.to_file()
        except Exception as e:
            logger.error(e)
            print('to_file failed!')


def runner():
    f = open('clients.json')
    clients = json.load(f)

    for c in clients['clients']:
        address = c['address']
        marketing_wallet = c['marketing_wallet']
        rewards_contract = c['rewards_contract']
        rewarded_token_contract_address = c['rewarded_token_contract']
        burn_address = c['burn_address']
        lp_address = c['lp_address']
        token = Token(address=address, marketing_wallet=marketing_wallet, rewards_contract=rewards_contract,
                      rewarded_token_contract_address=rewarded_token_contract_address, burn_address=burn_address, lp_address=lp_address)
        token.synchronize_data()

runner()
