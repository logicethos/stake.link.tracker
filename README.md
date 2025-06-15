# Stake.link Rewards Tracker
### Do your taxes!

This Python script fetches and tracks wallet balances for LINK and stLINK tokens, including staked and queued tokens in a priority pool, on the Ethereum mainnet. It retrieves data at specific blocks, including transaction blocks, weekly snapshots (every Monday at 13:00 UTC), and reward update blocks, and can output results in a human-readable format or as CSV.

## Features
- **Wallet Balance Tracking**: Retrieves LINK and stLINK token balances for a specified wallet.
- **Priority Pool Data**: Fetches staked (lsd_tokens) and queued (queued_tokens) amounts from a staking contract.
- **Reward Calculation**: Calculates rewards for reward update blocks based on changes in staked and queued tokens.
- **Block Selection**:
  - Token transfer transactions between the wallet and the staking contract.
  - Weekly snapshots every Monday at 13:00 UTC.
  - Reward update transactions on the rebase controller contract.
- **Output Options**: Supports human-readable output or CSV format for data analysis.
- **IPFS Integration**: Retrieves distribution and shares data from IPFS using the staking contract's IPFS hash.
- **Etherscan API**: Queries token transfers and reward update transactions.
- **Configurable Dates**: Allows specifying a start date for data retrieval (defaults to 2023-10-19).

## Prerequisites
- **Python 3.8+**
- **Dependencies** (install via `pip install -r requirements.txt`):
  - `web3`
  - `requests`
  - `base58`
  - `decimal`
  - `pytz`
- **Ethereum RPC Endpoint**: An Ethereum mainnet RPC URL (e.g., Alchemy).
- **Etherscan API Key**: For querying transaction data.
- **Environment Variables** (optional, override defaults in code):
  - `RPC_URL`: Ethereum RPC endpoint URL.
  - `ETHERSCAN_API_KEY`: Etherscan API key.
  - `USER_WALLET_ADDRESS`: Wallet address to track.

## Setup
1. **Clone the Repository**:
   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables** (optional):
   Create a `.env` file or set environment variables:
   ```bash
   export RPC_URL="https://eth-mainnet.g.alchemy.com/v2/your-api-key"
   export ETHERSCAN_API_KEY="your-etherscan-api-key"
   export USER_WALLET_ADDRESS="0xYourWalletAddress"
   ```

4. **Update Configuration** (if not using environment variables):
   Edit the script to set:
   - `RPC_URL`
   - `ETHERSCAN_API_KEY`
   - `USER_WALLET_ADDRESS`

## Usage
Run the script with optional arguments:

```bash
python script.py [--datefrom YYYY-MM-DD] [--csv]
```

- `--datefrom`: Start date for data retrieval (format: YYYY-MM-DD, default: 2023-10-19).
- `--csv`: Output results as CSV to stdout and suppress other output.

### Examples
- **Default Run** (human-readable output, starts from 2023-10-19):
  ```bash
  python script.py
  ```

- **Custom Start Date**:
  ```bash
  python script.py --datefrom 2024-01-01
  ```

- **CSV Output**:
  ```bash
  python script.py --csv > output.csv
  ```

### Output
- **Human-Readable**:
  Displays balances and rewards for each block, including:
  - Block number and date.
  - Wallet balances (stLINK, LINK).
  - Priority pool data (stLINK, queued LINK).
  - Rewards for reward blocks.

- **CSV**:
  Columns: `block_date`, `block`, `type`, `stlink_balance`, `link_balance`, `lsd_tokens`, `queued_tokens`, `reward_share`.

## Configuration Details
- **Contracts**:
  - Staking Contract: `0xDdC796a66E8b83d0BcCD97dF33A6CcFBA8fd60eA`
  - LINK Token: `0x514910771AF9Ca656af840dff83E8264EcF986CA`
  - stLINK Token: `0xb8b295df2cd735b15BE5Eb419517Aa626fc43cD5`
  - Rebase Controller: `0x1711e93eec78ba83D38C26f0fF284eB478bdbec4`
- **Default Start Block**: 18385225 (corresponding to 2023-10-19).
- **Snapshot Time**: 13:00:00 UTC every Monday (extra hour in case it's late).
- **Etherscan API**: Used for token transfers and reward updates.
- **IPFS Gateway**: `https://ipfs.io/ipfs/` for fetching distribution data.

## Notes
- Ensure your RPC endpoint and Etherscan API key are valid and have sufficient quotas.
- The script caches block timestamps to optimize performance.
- Errors (e.g., missing IPFS data, contract call failures) are logged unless `--csv` is used.
- The script stops processing after February 24, 2025, for Monday snapshots.
- Reward calculations assume previous block data is available for comparison.

## Troubleshooting
- **Connection Errors**: Verify `RPC_URL` and internet connectivity.
- **Etherscan API Errors**: Check `ETHERSCAN_API_KEY` and API rate limits.
- **IPFS Errors**: Ensure the IPFS gateway is accessible and the contract's IPFS hash is valid.
- **No Transactions Found**: Confirm `USER_WALLET_ADDRESS` and `STAKE_CONTRACT_ADDRESS` are correct.

## License
MIT License

## Contributing
Contributions are welcome! Please submit issues or pull requests for bug fixes or enhancements.