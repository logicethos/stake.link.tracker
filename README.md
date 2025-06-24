# Stake.link Rewards Tracker
### Do your taxes!

This Python script fetches and tracks wallet balances for LINK and stLINK tokens, including staked and queued tokens in a priority pool, on the Ethereum mainnet. It retrieves data at specific blocks, including transaction blocks, and reward update blocks, and can output results in a human-readable format or as CSV. 
Optional Google Sheets integration.

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

3. **Configure Environment Variables** :
   Or create a stLink.sh script (see stLink.sh_EXAMPLE):
   ```bash
   export RPC_URL="https://eth-mainnet.g.alchemy.com/v2/your-api-key"
   export ETHERSCAN_API_KEY="your-etherscan-api-key"
   export USER_WALLET_ADDRESS="0xYourWalletAddress"
   python stLink.py
   ```


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

## Google Cloud & Sheets Setup - OPTIONAL

To allow the application to automatically update a Google Sheet, you must authorize it using a Google Cloud Service Account. This is a one-time setup process.

### Step 1: Create a Google Cloud Project & Enable APIs

1.  Go to the [Google Cloud Console](https://console.cloud.google.com/).
2.  If you don't have a project, create a **New Project**. Give it a descriptive name (e.g., `My App Integrations`).
3.  Once in your project, go to the **APIs & Services** dashboard.
4.  Click **+ ENABLE APIS AND SERVICES**.
5.  Search for and **enable** the following two APIs:
    *   **Google Sheets API**
    *   **Google Drive API** (this is required for finding sheets by name/ID)

### Step 2: Create a Service Account

A service account is a special type of Google account intended to represent a non-human user that needs to authenticate and be authorized to access data in Google APIs.

1.  In the **APIs & Services** section, navigate to **Credentials**.
2.  Click **+ CREATE CREDENTIALS** and select **Service account**.
3.  Fill in the details:
    *   **Service account name:** A short name (e.g., `google-sheets-updater`).
    *   **Service account ID:** This will be automatically generated.
    *   **Description:** A clear description (e.g., "Service account to update project data in Google Sheets").
4.  Click **CREATE AND CONTINUE**.
5.  **Grant access (Permissions):** In the "Grant this service account access to project" step, select the **Editor** role for simplicity. This provides sufficient permissions. Click **CONTINUE**, then **DONE**.

### Step 3: Generate a JSON Key

You need a private key file for your application to authenticate as the service account.

1.  On the **Credentials** page, find the service account you just created in the "Service Accounts" list and click on it.
2.  Go to the **KEYS** tab.
3.  Click **ADD KEY** -> **Create new key**.
4.  Select **JSON** as the key type and click **CREATE**.
5.  A JSON file will be downloaded to your computer. **This file is a secret credential—treat it like a password!**
6.  Move this file into your project directory and rename it to `service-account-key.json` (or another name of your choice). **Do not commit this file to public Git repositories.** Add it to your `.gitignore` file.

### Step 4: Share Your Google Sheet

Finally, you must give your new service account permission to edit the specific Google Sheet you want to update.

1.  Open your downloaded `service-account-key.json` file in a text editor.
2.  Find the `client_email` address. It will look something like `your-account-name@your-project-id.iam.gserviceaccount.com`. Copy this email address.
3.  Open the target Google Sheet.
4.  Click the **Share** button in the top-right corner.
5.  Paste the `client_email` into the "Add people and groups" field.
6.  Ensure it is given **Editor** permissions.
7.  Click **Send**. You do not need to check the "Notify people" box.

Your setup is now complete. The application can use the JSON key to securely access and update the shared Google Sheet.

### Step 5: Update python script.

1. Edit stLink.sh
2. Add URL of your spreadsheet.

## License
MIT License

## Contributing
Contributions are welcome! Please submit issues or pull requests for bug fixes or enhancements.
