from web3 import Web3
from decimal import Decimal
import base58
import requests
import argparse
from datetime import datetime, timedelta
import pytz
import csv
import sys
import os
import time
import shelve

# --- CONFIGURATION ---
RPC_URL = "https://eth-mainnet.g.alchemy.com/v2/??????????"
ETHERSCAN_API_KEY = "?????"
USER_WALLET_ADDRESS = "0x15d11b????????????????"

# --- Overrides ---
RPC_URL = os.environ.get("RPC_URL", RPC_URL)
ETHERSCAN_API_KEY = os.environ.get("ETHERSCAN_API_KEY", ETHERSCAN_API_KEY)
USER_WALLET_ADDRESS = os.environ.get("USER_WALLET_ADDRESS", USER_WALLET_ADDRESS)

# --- Defaults ---
STAKE_CONTRACT_ADDRESS = "0xDdC796a66E8b83d0BcCD97dF33A6CcFBA8fd60eA"
LINK_TOKEN_ADDRESS = "0x514910771AF9Ca656af840dff83E8264EcF986CA"
stLINK_TOKEN_ADDRESS = "0xb8b295df2cd735b15BE5Eb419517Aa626fc43cD5"
REBASE_CONTROLLER_ADDRESS = "0x1711e93eec78ba83D38C26f0fF284eB478bdbec4"
TIME_OF_DAY = "13:00:00"
DEFAULT_START_DATE = "2023-10-19"
DEFAULT_START_BLOCK = 18385225

# --- CONTRACT ABI for the Data Provider ---
DATA_PROVIDER_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "getFullAccountData",
        "outputs": [
            {
                "components": [
                    {"internalType": "uint256", "name": "totalStaked", "type": "uint256"},
                    {"internalType": "uint256", "name": "totalRewards", "type": "uint256"},
                    {"internalType": "bool", "name": "isDelegated", "type": "bool"},
                    {"internalType": "uint32", "name": "operatorId", "type": "uint32"},
                    {"internalType": "uint32", "name": "nextOperatorId", "type": "uint32"},
                    {"internalType": "uint64", "name": "migrationDeadline", "type": "uint64"},
                ],
                "internalType": "struct StakingPoolDataProvider.FullAccountData",
                "name": "data",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "ipfsHash",
        "outputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "_account", "type": "address"},
            {"internalType": "uint256", "name": "_distributionShareAmount", "type": "uint256"}
        ],
        "name": "getLSDTokens",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {"internalType": "address", "name": "_account", "type": "address"},
            {"internalType": "uint256", "name": "_distributionAmount", "type": "uint256"}
        ],
        "name": "getQueuedTokens",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [],
        "name": "rebaseController",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# --- Minimal ERC-20 ABI for balanceOf ---
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function"
    }
]

# Initialize Web3 connection
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# Verify connection
if not w3.is_connected():
    raise ConnectionError("Failed to connect to Ethereum network")

# Contract instances
data_provider_contract = w3.eth.contract(address=w3.to_checksum_address(STAKE_CONTRACT_ADDRESS), abi=DATA_PROVIDER_ABI)
link_token_contract = w3.eth.contract(address=w3.to_checksum_address(LINK_TOKEN_ADDRESS), abi=ERC20_ABI)
stlink_token_contract = w3.eth.contract(address=w3.to_checksum_address(stLINK_TOKEN_ADDRESS), abi=ERC20_ABI)

def uint256_to_decimal(n: int, decimals: int = 18) -> Decimal:
    return Decimal(n) / (10 ** decimals)

block_timestamp_cache = {}


def get_block_number_for_timestamp(w3, target_timestamp):
    latest_block = w3.eth.get_block('latest')
    latest_timestamp = latest_block['timestamp']
    latest_number = latest_block['number']

    if target_timestamp > latest_timestamp:
        raise ValueError("Target timestamp is in the future")

    low = DEFAULT_START_BLOCK
    high = latest_number
    while low < high:
        mid = (low + high) // 2
        if mid in block_timestamp_cache:
            mid_timestamp = block_timestamp_cache[mid]
        else:
            mid_block = w3.eth.get_block(mid)
            mid_timestamp = mid_block['timestamp']
            block_timestamp_cache[mid] = mid_timestamp
        if mid_timestamp < target_timestamp:
            low = mid + 1
        else:
            high = mid
    if low not in block_timestamp_cache:
        block_timestamp_cache[low] = w3.eth.get_block(low)['timestamp']
    return low

def get_block_timestamp(block_num):
    with shelve.open('block_timestamp_cache.db') as cache:
        if str(block_num) in cache:  # Keys must be strings in Shelve
            return cache[str(block_num)]
        else:
            timestamp = w3.eth.get_block(block_num)['timestamp']
            cache[str(block_num)] = timestamp
            return timestamp

def get_link_price(date: str, csv_mode: bool = False) -> float:
    with shelve.open('price_cache.db') as cache:
        if date in cache:
            return cache[date]
        
        max_retries = 10
        retry_count = 0
        
        while retry_count < max_retries:
            time.sleep(1)  # 1-second delay for every request
            
            try:
                url = f"https://api.coingecko.com/api/v3/coins/chainlink/history?date={date}&localization=false"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 429:
                    retry_count += 1
                    time.sleep(10)
                    if not csv_mode:
                        print(f"Rate limit hit for {date}, retry {retry_count}/{max_retries}", file=sys.stderr)
                    continue
                    
                response.raise_for_status()
                data = response.json()
                
                price = float(data['market_data']['current_price']['usd'])
                cache[date] = price  # Store in Shelve
                return price
                
            except requests.exceptions.RequestException as e:
                if not csv_mode:
                    print(f"Error fetching LINK price for {date}: {e}", file=sys.stderr)
                return 0.0
            except Exception as e:
                if not csv_mode:
                    print(f"Unexpected error fetching LINK price for {date}: {e}", file=sys.stderr)
                return 0.0
        
        if not csv_mode:
            print(f"Max retries reached for {date}", file=sys.stderr)
        return 0.0

def fetch_ipfs_data(cid: str, wallet_address: str, csv_mode: bool = False) -> tuple[int, int]:
    gateway_url = f"https://ipfs.io/ipfs/{cid}"
    try:
        response = requests.get(gateway_url, timeout=10)
        response.raise_for_status()
        ipfs_text = response.text.lower()
        
        start_index = ipfs_text.find(wallet_address.lower())
        if start_index == -1:
            if not csv_mode:
                print(f"Address {wallet_address} not found in IPFS data (yet)")
            return 0, 0
            
        brace_start = ipfs_text.find("{", start_index)
        if brace_start == -1:
            raise ValueError("Malformed data: No opening brace found after address")
            
        brace_count = 1
        end_index = brace_start + 1
        while end_index < len(ipfs_text) and brace_count > 0:
            if ipfs_text[end_index] == "{":
                brace_count += 1
            elif ipfs_text[end_index] == "}":
                brace_count -= 1
            end_index += 1
            
        if brace_count != 0:
            raise ValueError("Malformed data: Mismatched braces")
            
        data_str = ipfs_text[brace_start:end_index].replace('\\"', '"')
        
        amount_start = data_str.find('"amount":"') + len('"amount":"')
        amount_end = data_str.find('"', amount_start)
        distribution_amount = int(data_str[amount_start:amount_end], 0)
        
        shares_start = data_str.find('"sharesamount":"') + len('"sharesamount":"')
        shares_end = data_str.find('"', shares_start)
        shares_amount = int(data_str[shares_start:shares_end], 0)
        
        return distribution_amount, shares_amount
        
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Error fetching IPFS data: {e}")
    except ValueError as e:
        raise ValueError(f"Invalid amount or sharesAmount value: {e}")

def get_wallet_balances(wallet_address: str, block_number: int, csv_mode: bool = False) -> dict:
    checksum_wallet = w3.to_checksum_address(wallet_address)
    
    result = {
        'stlink_balance': -1,
        'link_balance': -1,
        'lsd_tokens': 0,
        'queued_tokens': 0
    }
    
    try:
        raw_hash = data_provider_contract.functions.ipfsHash().call(block_identifier=block_number)
        prefix = bytes([0x12, 0x20])
        full_multihash = prefix + raw_hash
        cid = base58.b58encode(full_multihash).decode('utf-8')
        
        distribution_amount, shares_amount = fetch_ipfs_data(cid, wallet_address, csv_mode)
        
        result['lsd_tokens'] = data_provider_contract.functions.getLSDTokens(
            checksum_wallet, shares_amount
        ).call(block_identifier=block_number)
        
        result['queued_tokens'] = data_provider_contract.functions.getQueuedTokens(
            checksum_wallet, distribution_amount
        ).call(block_identifier=block_number)
                
    except Exception as e:
        if not csv_mode:
            print(f"Error processing IPFS or contract calls at block {block_number}: {e}")
    
    try:
        result['stlink_balance'] = stlink_token_contract.functions.balanceOf(
            checksum_wallet
        ).call(block_identifier=block_number)
    except Exception as e:
        if not csv_mode:
            print(f"Error querying stLINK balance at block {block_number}: {e}")
    
    try:
        result['link_balance'] = link_token_contract.functions.balanceOf(
            checksum_wallet
        ).call(block_identifier=block_number)
    except Exception as e:
        if not csv_mode:
            print(f"Error querying LINK balance at block {block_number}: {e}")
    
    return result

def fetch_token_transactions(wallet_address: str, STAKE_CONTRACT_ADDRESS: str, start_block: int, csv_mode: bool = False) -> list[tuple[int, str]]:
    wallet_addr_lower = wallet_address.lower()
    counterparty_addr_lower = STAKE_CONTRACT_ADDRESS.lower()

    params = {
        "module": "account",
        "action": "tokentx",
        "address": wallet_address,
        "startblock": start_block,
        "endblock": 99999999,
        "sort": "asc",
        "apikey": ETHERSCAN_API_KEY
    }

    try:
        response = requests.get("https://api.etherscan.io/api", params=params)
        response.raise_for_status()
        data = response.json()

        if data['status'] == '0':
            if not csv_mode:
                print(f"Etherscan API Message: {data['message']}")
                print(f"Result: {data.get('result', 'N/A')}")
            return []

        transactions = data['result']
        block_types = set()

        for tx in transactions:
            tx_from = tx['from'].lower()
            tx_to = tx['to'].lower()

            is_outgoing = (tx_from == wallet_addr_lower and tx_to == counterparty_addr_lower)
            is_incoming = (tx_from == counterparty_addr_lower and tx_to == wallet_addr_lower)

            if is_outgoing or is_incoming:
                block_number = int(tx['blockNumber'])
                tx_type = "Stake" if is_outgoing else "Withdraw"
                block_types.add((block_number, tx_type))
                if not csv_mode:
                    token_symbol = tx['tokenSymbol']
                    print(f"Found {tx_type} transfer of {token_symbol} in Block #{tx['blockNumber']} from {tx['from']} to {tx['to']}")

        return list(block_types)

    except requests.exceptions.RequestException as e:
        if not csv_mode:
            print(f"An error occurred while calling the Etherscan API: {e}")
        return []
    except Exception as e:
        if not csv_mode:
            print(f"An unexpected error occurred: {e}")
        return []

def fetch_update_rewards_blocks(rebase_controller_address: str, start_block: int, method_id: str, csv_mode: bool = False) -> list[tuple[int, str]]:
    rebase_controller_lower = rebase_controller_address.lower()
    params = {
        "module": "account",
        "action": "txlist",
        "address": rebase_controller_address,
        "startblock": start_block,
        "endblock": 99999999,
        "sort": "asc",
        "apikey": ETHERSCAN_API_KEY
    }    
    try:
        response = requests.get("https://api.etherscan.io/api", params=params)
        response.raise_for_status()
        data = response.json()
        if data['status'] == '0':
            if not csv_mode:
                print(f"Etherscan API Message: {data['message']}")
                print(f"Result: {data.get('result', 'N/A')}")
            return []
        blocks = set()
        for tx in data['result']:
            if tx['to'].lower() == rebase_controller_lower and tx['input'].startswith(method_id):
                block_number = int(tx['blockNumber'])
                blocks.add((block_number, "Rewards"))
                if not csv_mode:
                    print(f"Found 'Rewards' transaction in Block #{tx['blockNumber']}")
        return list(blocks)
    except Exception as e:
        if not csv_mode:
            print(f"Error fetching 'Rewards' transactions: {e}")
        return []

def get_monday_block_numbers(start_date: datetime, end_date: datetime, TIME_OF_DAY: str) -> list[tuple[int, str]]:
    blocks = []
    utc = pytz.UTC
    time_parts = list(map(int, TIME_OF_DAY.split(":")))
    target_time = timedelta(hours=time_parts[0], minutes=time_parts[1], seconds=time_parts[2])
    
    current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    while current_date <= end_date:
        if current_date.weekday() == 0:
            target_datetime = current_date + target_time
            if start_date <= target_datetime < end_date:
                timestamp = int(target_datetime.timestamp())
                block_number = get_block_number_for_timestamp(w3, timestamp)
                blocks.append((block_number, "Rewards"))
        current_date += timedelta(days=1)
    
    return blocks

def main():
    parser = argparse.ArgumentParser(description="Fetch wallet balances at specific blocks")
    parser.add_argument(
        "--datefrom",
        type=str,
        default=DEFAULT_START_DATE,
        help="Start date for search (YYYY-MM-DD, default: 2023-10-19)"
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Output results as CSV to stdout and suppress other output"
    )
    args = parser.parse_args()

    try:
        utc = pytz.UTC
        default_start_date = datetime.strptime(DEFAULT_START_DATE, "%Y-%m-%d").replace(tzinfo=utc)
        monday_end_date = datetime(2025, 2, 24, 0, 0, 0, tzinfo=utc)

        if args.datefrom == DEFAULT_START_DATE:
            start_timestamp = int(default_start_date.timestamp())
            start_block = get_block_number_for_timestamp(w3, start_timestamp)
            
            transaction_blocks = fetch_token_transactions(
                USER_WALLET_ADDRESS,
                STAKE_CONTRACT_ADDRESS,
                start_block,
                args.csv
            )
            
            if not transaction_blocks:
                if not args.csv:
                    raise ValueError("No transactions found for the given wallet and data provider since default_start_date")
                else:
                    return
            
            earliest_block = min(block_num for block_num, _ in transaction_blocks)
            earliest_timestamp = w3.eth.get_block(earliest_block).timestamp
            start_date = datetime.fromtimestamp(earliest_timestamp, tz=utc)
        else:
            start_date = datetime.strptime(args.datefrom, "%Y-%m-%d").replace(tzinfo=utc)
            start_timestamp = int(start_date.timestamp())
            start_block = get_block_number_for_timestamp(w3, start_timestamp)
            
            transaction_blocks = fetch_token_transactions(
                USER_WALLET_ADDRESS,
                STAKE_CONTRACT_ADDRESS,
                start_block,
                args.csv
            )
        
        monday_blocks = get_monday_block_numbers(start_date, monday_end_date, TIME_OF_DAY)
        
        method_id = "0x128606a6"
        update_rewards_blocks = fetch_update_rewards_blocks(REBASE_CONTROLLER_ADDRESS, start_block, method_id, args.csv)
        
        all_blocks = sorted(
            monday_blocks +
            transaction_blocks +
            update_rewards_blocks,
            key=lambda x: x[0]
        )
        
        if args.csv:
            writer = csv.writer(sys.stdout, lineterminator='\n')
            writer.writerow(['block_date', 'block', 'type', 'stlink_balance', 'link_balance', 'lsd_tokens', 'queued_tokens', 'reward_share', 'link_price_usd'])
        else:
            print(f"\n=== Balances for {USER_WALLET_ADDRESS} at {len(all_blocks)} blocks ===")
        
        previous_stlink_balance_uint = None
        previous_lsd_tokens_uint = None
        previous_queued_tokens_uint = None
        for block_num, block_type in all_blocks:
            try:
                block_timestamp = get_block_timestamp(block_num)
                block_date = datetime.fromtimestamp(block_timestamp, tz=utc)
                block_date_str = block_date.strftime("%Y-%m-%d %H:%M:%S")
                price_date = block_date.strftime("%d-%m-%Y")
                
                balances = get_wallet_balances(USER_WALLET_ADDRESS, block_num, args.csv)
                
                stlink_balance_uint = uint256_to_decimal(balances['stlink_balance'])
                lsd_tokens_uint = uint256_to_decimal(balances['lsd_tokens'])
                queued_tokens_uint = uint256_to_decimal(balances['queued_tokens'])
                
                reward = Decimal(0)
                if block_type == "Rewards":
                    if previous_lsd_tokens_uint is not None:
                       reward = (stlink_balance_uint - previous_stlink_balance_uint) + (lsd_tokens_uint - previous_lsd_tokens_uint) - (previous_queued_tokens_uint - queued_tokens_uint)
                    else:
                       continue
                
                link_price = get_link_price(price_date, args.csv) if block_type == "Rewards" else 0.0
                
                previous_stlink_balance_uint = stlink_balance_uint
                previous_lsd_tokens_uint = lsd_tokens_uint
                previous_queued_tokens_uint = queued_tokens_uint
                
                if args.csv:
                    writer.writerow([
                        block_date_str,
                        block_num,
                        block_type,
                        str(stlink_balance_uint),
                        str(uint256_to_decimal(balances['link_balance'])),
                        str(lsd_tokens_uint),
                        str(queued_tokens_uint),
                        f"{reward:.8f}",
                        f"{link_price:.2f}"
                    ])
                else:
                    print(f"\nBlock {block_num} (Date: {block_date_str}, Type: {block_type})")
                    print(f"Wallet:")
                    print(f"  stLINK: {stlink_balance_uint}")
                    print(f"  LINK: {uint256_to_decimal(balances['link_balance'])}")
                    print(f"Priority Pool:")
                    print(f"  stLINK: {lsd_tokens_uint}")
                    print(f"  LINK: {queued_tokens_uint} (Queued)")
                    if block_type == "Rewards":
                        print(f"  Reward: {reward:.8f}")
                        print(f"  LINK Price (USD): {link_price:.2f}")
            except Exception as e:
                if not args.csv:
                    print(f"Error processing block {block_num}: {e}")
                continue
    except ValueError as e:
        if not args.csv:
            print(f"Error: {e}")
        exit(1)
    except Exception as e:
        if not args.csv:
            print(f"Unexpected error: {e}")
        exit(1)

if __name__ == "__main__":
    main()
