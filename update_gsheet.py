import sys
import os
import csv
import re
import gspread
import argparse
from datetime import datetime
from google.oauth2.service_account import Credentials
import signal

# --- Robustly handle BrokenPipeError for command-line usage ---
try:
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (AttributeError, ValueError):
    # signal.SIGPIPE is not available on all platforms (e.g., Windows).
    pass
# ---------------------------------------------------------------

# --- Configuration & Constants ---
SPREADSHEET_URL = os.getenv('GOOGLE_SHEET_URL')
WORKSHEET_NAME = os.getenv('GOOGLE_SHEET_TAB_NAME', 'stLink Data')
SERVICE_ACCOUNT_FILE = os.getenv('GCP_SERVICE_ACCOUNT_FILE')

# Base list of numerical columns, the dynamic price column will be added to this.
BASE_NUMERICAL_COLUMNS = ['stlink_balance','link_balance','lsd_tokens','queued_tokens','reward_share']

UNIQUE_ID_COLUMN = 'block'
DATE_COLUMN_NAME = 'block_date'
PERMISSION_ERROR_EXIT_CODE = 3

# --- New Constants for the Report Tab ---
REPORT_WORKSHEET_NAME = "stLink Monthly"
REPORT_TAB_REWARD_HEADER = "stLink Reward"


def extract_spreadsheet_id_from_url(url):
    """Extracts the spreadsheet ID from a Google Sheets URL using regex."""
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
    return match.group(1) if match else None

def col_index_to_letter(col_index):
    """Converts a 0-indexed column number to its letter representation (e.g., 0 -> A, 26 -> AA)."""
    letter = ""
    while col_index >= 0:
        col_index, remainder = divmod(col_index, 26)
        letter = chr(65 + remainder) + letter
        col_index -= 1
    return letter

def connect_to_gsheet():
    """Authenticates and connects to the Google Sheet. Returns a worksheet object for the main data tab."""
    if not all([SPREADSHEET_URL, WORKSHEET_NAME, SERVICE_ACCOUNT_FILE]):
        print("Error: Missing one or more required environment variables:", file=sys.stderr)
        print("  - GOOGLE_SHEET_URL, GOOGLE_SHEET_TAB_NAME, GCP_SERVICE_ACCOUNT_FILE", file=sys.stderr)
        sys.exit(1)

    spreadsheet_id = extract_spreadsheet_id_from_url(SPREADSHEET_URL)
    if not spreadsheet_id:
        print(f"Error: Could not extract a valid Spreadsheet ID from the URL.", file=sys.stderr)
        sys.exit(1)

    print("Connecting to Google Sheets...", file=sys.stderr)
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(spreadsheet_id)
        
        try:
            worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            print(f"Worksheet '{WORKSHEET_NAME}' not found. Creating it...", file=sys.stderr)
            worksheet = spreadsheet.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=20)
            
        return worksheet
        
    except PermissionError:
        print(f"\nFATAL: A file system PermissionError occurred.", file=sys.stderr)
        print(f"The script was denied permission to read the key file: '{SERVICE_ACCOUNT_FILE}'", file=sys.stderr)
        print("Please check the file and directory permissions.", file=sys.stderr)
        sys.exit(PERMISSION_ERROR_EXIT_CODE)
    except FileNotFoundError:
        print(f"Error: Service account key file not found at '{SERVICE_ACCOUNT_FILE}'", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred during connection:", file=sys.stderr)
        print(f"ERROR DETAILS: {repr(e)}\n", file=sys.stderr)
        sys.exit(1)

def convert_to_number(value):
    """Convert a string to int or float if it represents a number, else return unchanged."""
    if not isinstance(value, str) or not value.strip():
        return value
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value

def handle_get_last_date(worksheet):
    """Finds, formats, and prints the latest date from the specified date column."""
    print(f"Fetching header from '{worksheet.title}' to find '{DATE_COLUMN_NAME}' column...", file=sys.stderr)
    try:
        header = worksheet.row_values(1)
    except gspread.exceptions.APIError as e:
        print(f"Error fetching header: {e}", file=sys.stderr)
        sys.exit(1)

    if not header:
        print("Sheet appears to be empty. No date to return.", file=sys.stderr)
        return

    try:
        date_col_index = header.index(DATE_COLUMN_NAME) + 1
    except ValueError:
        print(f"Error: Date column '{DATE_COLUMN_NAME}' not found in the sheet header.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching dates from column {date_col_index}...", file=sys.stderr)
    dates_str = worksheet.col_values(date_col_index)[1:]
    
    last_date = None
    for date_str in dates_str:
        if not date_str: continue
        try:
            current_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
            if last_date is None or current_date > last_date:
                last_date = current_date
        except ValueError:
            continue

    if last_date:
        print(last_date.strftime('%Y-%m-%d'))
    else:
        print("No valid dates found in the column.", file=sys.stderr)

def handle_update_sheet(worksheet):
    """Reads CSV from stdin and appends new, unique rows to the sheet with proper numerical and date types."""
    print("Reading new data from stdin...", file=sys.stderr)
    stdin_data = sys.stdin.read()
    if not stdin_data.strip():
        print("No input data received. Exiting.", file=sys.stderr)
        return

    csv_reader = csv.reader(stdin_data.strip().splitlines())
    new_data_rows = list(csv_reader)
    if not new_data_rows:
        print("CSV data is empty. Exiting.", file=sys.stderr)
        return
    new_header = new_data_rows[0]

    all_numerical_cols = BASE_NUMERICAL_COLUMNS.copy()
    dynamic_price_col = next((col for col in new_header if col.startswith('link_price_')), None)
    
    if dynamic_price_col:
        print(f"Found dynamic price column in CSV data: '{dynamic_price_col}'", file=sys.stderr)
        all_numerical_cols.append(dynamic_price_col)
    else:
        print("Warning: No column starting with 'link_price_' found in the input CSV.", file=sys.stderr)
        
    numerical_col_indices = []
    try:
        numerical_col_indices = [new_header.index(col) for col in all_numerical_cols]
    except ValueError as e:
        print(f"Warning: A numerical column was not found in the CSV header: {e}", file=sys.stderr)

    try:
        date_col_index = new_header.index(DATE_COLUMN_NAME)
    except ValueError:
        print(f"Warning: Date column '{DATE_COLUMN_NAME}' not found in header.", file=sys.stderr)
        date_col_index = None

    converted_rows = [new_data_rows[0]]
    for row in new_data_rows[1:]:
        new_row = row.copy()
        for col_idx in numerical_col_indices:
            if len(new_row) > col_idx:
                new_row[col_idx] = convert_to_number(new_row[col_idx])
        if date_col_index is not None and len(new_row) > date_col_index and new_row[date_col_index].strip():
            try:
                parsed_date = datetime.strptime(new_row[date_col_index], '%Y-%m-%d %H:%M:%S')
                new_row[date_col_index] = parsed_date.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                print(f"Warning: Could not parse date '{new_row[date_col_index]}' in row {row}. Keeping as string.", file=sys.stderr)
        converted_rows.append(new_row)

    print(f"Fetching existing data from tab '{worksheet.title}'...", file=sys.stderr)
    existing_data = worksheet.get_all_values()
    
    rows_to_append = []
    if not existing_data:
        print("Sheet is empty. Adding all new data.", file=sys.stderr)
        rows_to_append = converted_rows
    else:
        existing_header = existing_data[0]
        try:
            unique_id_col_index = existing_header.index(UNIQUE_ID_COLUMN)
            existing_ids = {row[unique_id_col_index] for row in existing_data[1:] if len(row) > unique_id_col_index}
            print(f"Found {len(existing_ids)} existing unique IDs.", file=sys.stderr)
            new_unique_id_col_index = new_header.index(UNIQUE_ID_COLUMN)
            for row in converted_rows[1:]:
                if len(row) > new_unique_id_col_index and row[new_unique_id_col_index] not in existing_ids:
                    rows_to_append.append(row)
        except (ValueError, IndexError):
            print(f"Warning: Could not find '{UNIQUE_ID_COLUMN}' in header or data is inconsistent.", file=sys.stderr)
            print("Clearing the sheet and adding all new data to ensure consistency.", file=sys.stderr)
            worksheet.clear()
            rows_to_append = converted_rows
    
    if rows_to_append:
        print(f"Appending {len(rows_to_append)} new rows...", file=sys.stderr)
        worksheet.append_rows(rows_to_append, value_input_option='USER_ENTERED')
        
        if date_col_index is not None:
            spreadsheet = worksheet.spreadsheet
            sheet_id = worksheet.id
            requests = [
                {
                    'repeatCell': {
                        'range': {
                            'sheetId': sheet_id, 'startRowIndex': 1, 'endRowIndex': 1000,
                            'startColumnIndex': date_col_index, 'endColumnIndex': date_col_index + 1
                        },
                        'cell': {'userEnteredFormat': {'numberFormat': {'type': 'DATE', 'pattern': 'yyyy-mm-dd hh:mm:ss'}}},
                        'fields': 'userEnteredFormat.numberFormat'
                    }
                }
            ]
            print(f"Applying date format to column '{DATE_COLUMN_NAME}'...", file=sys.stderr)
            spreadsheet.batch_update({'requests': requests})
        
        print("Successfully updated the Google Sheet.", file=sys.stderr)
    else:
        print("No new rows to add. The sheet is already up-to-date.", file=sys.stderr)

def get_currency_symbol(header_name):
    """Extracts a currency symbol from a header string like 'link_price_usd'."""
    try:
        currency_code = header_name.split('_')[-1].upper()
    except (IndexError, AttributeError):
        return '$' 
        
    symbols = {
        'USD': '$', 'CAD': '$', 'AUD': '$',
        'EUR': '€',
        'GBP': '£',
        'JPY': '¥',
        'CHF': 'Fr'
    }
    return symbols.get(currency_code, '$')

def handle_setup_report_tab(spreadsheet, source_tab_name):
    """Creates/configures the 'Monthly Report' tab, dynamically finding the price column."""
    print(f"Attempting to set up the '{REPORT_WORKSHEET_NAME}' tab...", file=sys.stderr)
    
    source_worksheet = spreadsheet.worksheet(source_tab_name)
    header = source_worksheet.row_values(1)
    if not header:
        print(f"Error: Source tab '{source_tab_name}' is empty. Cannot set up report.", file=sys.stderr)
        sys.exit(1)
        
    price_col_index = next((i for i, col in enumerate(header) if col.startswith('link_price_')), -1)

    if price_col_index == -1:
        print(f"FATAL: Could not find a price column (e.g., 'link_price_usd') in the '{source_tab_name}' tab header.", file=sys.stderr)
        sys.exit(1)
        
    price_col_name = header[price_col_index]
    price_col_letter = col_index_to_letter(price_col_index)
    print(f"Found price column '{price_col_name}' in source tab at column {price_col_letter}.", file=sys.stderr)

    try:
        report_worksheet = spreadsheet.worksheet(REPORT_WORKSHEET_NAME)
        print(f"Found existing tab '{REPORT_WORKSHEET_NAME}'. It will be cleared and reconfigured.", file=sys.stderr)
    except gspread.exceptions.WorksheetNotFound:
        print(f"Tab '{REPORT_WORKSHEET_NAME}' not found. Creating it...", file=sys.stderr)
        report_worksheet = spreadsheet.add_worksheet(title=REPORT_WORKSHEET_NAME, rows=1000, cols=26)

    report_sheet_id = report_worksheet.id
    requests = []

    spreadsheet_metadata = spreadsheet.fetch_sheet_metadata()
    sheet_info = next((s for s in spreadsheet_metadata['sheets'] if s['properties']['sheetId'] == report_sheet_id), None)
    if sheet_info and 'slicers' in sheet_info:
        for slicer in sheet_info['slicers']:
            requests.append({'deleteEmbeddedObject': {'objectId': slicer['slicerId']}})

    report_worksheet.clear()

    # --- Define Formulas and Formats ---
    query_formula = f"=QUERY('{source_tab_name}'!A:G, \"SELECT * WHERE A IS NOT NULL\")"       
    reward_formula = (
        f"=ARRAYFORMULA(IF((A2:A <> \"\") * (TEXT(A2:A, \"YYYY-MM\") <> TEXT(A3:A, \"YYYY-MM\")), "
        f"SUMIF(TEXT(A2:A, \"YYYY-MM\"), TEXT(A2:A, \"YYYY-MM\"), '{source_tab_name}'!I2:I), \"\"))"
    )
    price_formula = f"=ARRAYFORMULA('{source_tab_name}'!{price_col_letter}2:{price_col_letter})"
    total_formula = f"=ARRAYFORMULA(IFERROR(ROUND(I2:I*H2:H,2)))"
    # ***IMPROVED FORMULA***: Prevents #DIV/0! errors if token counts are zero.
    apy_formula = f"=ARRAYFORMULA(IF((D2:D+F2:F)>0, (1 + I2:I/(D2:D+F2:F))^12 - 1, IFERROR(1/0)))"


    currency_symbol = get_currency_symbol(price_col_name)
    currency_format_pattern = f'"{currency_symbol}"#,##0.00'
    print(f"Using currency symbol '{currency_symbol}' for formatting.", file=sys.stderr)

    # --- Build Batch Update Request ---
    requests.extend([
        {'updateCells': {'rows': [{'values': [{'userEnteredValue': {'formulaValue': query_formula}}]}], 'fields': 'userEnteredValue', 'start': {'sheetId': report_sheet_id, 'rowIndex': 0, 'columnIndex': 0}}},
        {'updateCells': {'rows': [{'values': [{'userEnteredValue': {'formulaValue': price_formula}}]}], 'fields': 'userEnteredValue', 'start': {'sheetId': report_sheet_id, 'rowIndex': 1, 'columnIndex': 7}}},
        {'updateCells': {'rows': [{'values': [{'userEnteredValue': {'formulaValue': reward_formula}}]}], 'fields': 'userEnteredValue', 'start': {'sheetId': report_sheet_id, 'rowIndex': 1, 'columnIndex': 8}}},
        {'updateCells': {'rows': [{'values': [{'userEnteredValue': {'formulaValue': total_formula}}]}], 'fields': 'userEnteredValue', 'start': {'sheetId': report_sheet_id, 'rowIndex': 1, 'columnIndex': 9}}},
        {'updateCells': {'rows': [{'values': [{'userEnteredValue': {'formulaValue': apy_formula}}]}], 'fields': 'userEnteredValue', 'start': {'sheetId': report_sheet_id, 'rowIndex': 1, 'columnIndex': 10}}},
        
        {'updateCells': {'rows': [{'values': [{'userEnteredValue': {'stringValue': REPORT_TAB_REWARD_HEADER}}]}], 'fields': 'userEnteredValue', 'start': {'sheetId': report_sheet_id, 'rowIndex': 0, 'columnIndex': 8}}},
        {'updateCells': {'rows': [{'values': [{'userEnteredValue': {'stringValue': f'Monthly Reward {currency_symbol}'}}]}], 'fields': 'userEnteredValue', 'start': {'sheetId': report_sheet_id, 'rowIndex': 0, 'columnIndex': 9}}},
        {'updateCells': {'rows': [{'values': [{'userEnteredValue': {'stringValue': 'Est APY'}}]}], 'fields': 'userEnteredValue', 'start': {'sheetId': report_sheet_id, 'rowIndex': 0, 'columnIndex': 10}}},
        
        {'repeatCell': {'range': {'sheetId': report_sheet_id, 'startRowIndex': 1, 'endRowIndex': 1000, 'startColumnIndex': 0, 'endColumnIndex': 1}, 'cell': {'userEnteredFormat': {'numberFormat': {'type': 'DATE', 'pattern': 'yyyy mmm'}}}, 'fields': 'userEnteredFormat.numberFormat'}},
        {'repeatCell': {'range': {'sheetId': report_sheet_id, 'startRowIndex': 1, 'endRowIndex': 1000, 'startColumnIndex': 7, 'endColumnIndex': 8}, 'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': currency_format_pattern}}}, 'fields': 'userEnteredFormat.numberFormat'}},
        {'repeatCell': {'range': {'sheetId': report_sheet_id, 'startRowIndex': 1, 'endRowIndex': 1000, 'startColumnIndex': 8, 'endColumnIndex': 9}, 'cell': {'userEnteredFormat': {'numberFormat': {'type': 'NUMBER', 'pattern': '0.000'}}}, 'fields': 'userEnteredFormat.numberFormat'}},
        {'repeatCell': {'range': {'sheetId': report_sheet_id, 'startRowIndex': 1, 'endRowIndex': 1000, 'startColumnIndex': 9, 'endColumnIndex': 10}, 'cell': {'userEnteredFormat': {'numberFormat': {'type': 'CURRENCY', 'pattern': currency_format_pattern}}}, 'fields': 'userEnteredFormat.numberFormat'}},
        {'repeatCell': {'range': {'sheetId': report_sheet_id, 'startRowIndex': 1, 'endRowIndex': 1000, 'startColumnIndex': 10, 'endColumnIndex': 11}, 'cell': {'userEnteredFormat': {'numberFormat': {'type': 'PERCENT', 'pattern': '#0.00%'}}}, 'fields': 'userEnteredFormat.numberFormat'}}
    ])
    
    # ***CORRECTED SLICER***: Uses a condition to filter for numbers > 0, which correctly
    # excludes blanks, text, errors, and zero values.
    print("Adding slicer to filter for monthly rewards greater than zero...", file=sys.stderr)
    requests.append({
        'addSlicer': {
            'slicer': {
                'spec': {
                    'dataRange': {'sheetId': report_sheet_id, 'startColumnIndex': 0, 'endColumnIndex': 9},
                    'columnIndex': 8,
                    'title': "Filter by Reward",
                    'filterCriteria': {
                        'condition': {
                            'type': 'NUMBER_GREATER',
                            'values': [{'userEnteredValue': '0'}]
                        }
                    }
                },
                'position': {'overlayPosition': {'anchorCell': {'sheetId': report_sheet_id, 'rowIndex': 1, 'columnIndex': 11}}}
            }
        }
    })
                            
    requests.append({
        'updateSheetProperties': {'properties': {'sheetId': report_sheet_id, 'index': 0}, 'fields': 'index'}
    })

    if requests:
        print("Applying all changes in a single batch update...", file=sys.stderr)
        spreadsheet.batch_update({'requests': requests})
    
    print(f"Successfully configured tab '{REPORT_WORKSHEET_NAME}'.", file=sys.stderr)
    
def main():
    """Main function to parse arguments and delegate action."""
    parser = argparse.ArgumentParser(description="Update a Google Sheet from CSV data, get the last entry date, or set up a report tab.")
    parser.add_argument('--get-last-date', action='store_true', help="Print the latest date from the 'block_date' column and exit.")
    parser.add_argument('--setup-report-tab', action='store_true', help="Create and configure the 'Monthly Report' summary tab.")
    args = parser.parse_args()

    worksheet = connect_to_gsheet()
    
    if args.get_last_date:
        handle_get_last_date(worksheet)
    elif args.setup_report_tab:
        spreadsheet = worksheet.spreadsheet
        source_tab_name = worksheet.title
        handle_setup_report_tab(spreadsheet, source_tab_name)
    else:
        handle_update_sheet(worksheet)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nScript interrupted by user.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"\nAn unhandled error occurred in main: {repr(e)}", file=sys.stderr)
        sys.exit(1)
