from flask import Flask, render_template, abort, flash, redirect, url_for
import pandas as pd
import os # Import the os module for path handling
import logging # Import logging for better error tracking

app = Flask(__name__)
# It's good practice to set a secret key for Flask apps, especially if using flash messages
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a_default_secret_key_change_me')

# --- Configuration ---
# Get the directory where the script is running
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Define the path to the CSV relative to the script's location
# Place your CSV in the same directory as this Python script,
# or modify the path accordingly.
CSV_FILE_PATH = os.path.join(BASE_DIR, 'cleaned_data_with_predictions.csv')

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Global variable for DataFrame ---
dataframe_cleaned = None

# --- Function to load data safely ---
def load_data(file_path):
    """Loads the CSV data safely, handling potential errors."""
    global dataframe_cleaned
    try:
        if not os.path.exists(file_path):
            logging.error(f"Data file not found at: {file_path}")
            raise FileNotFoundError(f"Data file not found at: {file_path}")

        logging.info(f"Attempting to load data from: {file_path}")
        df = pd.read_csv(file_path)
        logging.info(f"Successfully loaded data with shape: {df.shape}")

        # --- Data Validation ---
        required_columns = [
            'ADDRESS', 'SUBLOCALITY', 'PRICE', 'PREDICTED_PRICE',
            'PRICE_DIFFERENCE', 'PROPERTYSQFT', 'BEDS', 'BATH'
        ]
        missing_cols = [col for col in required_columns if col not in df.columns]
        if missing_cols:
            error_msg = f"Missing required columns in CSV: {', '.join(missing_cols)}"
            logging.error(error_msg)
            raise ValueError(error_msg)

        # Optional: Handle potential NaN values if they cause issues later
        # Example: df.dropna(subset=['PRICE_DIFFERENCE', 'SUBLOCALITY'], inplace=True)

        dataframe_cleaned = df
        return True # Indicate success

    except FileNotFoundError:
        # Already logged above
        return False # Indicate failure
    except pd.errors.EmptyDataError:
        logging.error(f"CSV file is empty: {file_path}")
        dataframe_cleaned = pd.DataFrame() # Set to empty DataFrame
        return True # Technically loaded, but it's empty
    except pd.errors.ParserError:
        logging.error(f"Error parsing CSV file: {file_path}. Check file format.")
        return False # Indicate failure
    except ValueError as ve:
        # Already logged above (for missing columns)
         return False # Indicate failure
    except Exception as e:
        logging.error(f"An unexpected error occurred while loading data: {e}", exc_info=True)
        return False # Indicate failure

# --- Load data on startup ---
data_loaded_successfully = load_data(CSV_FILE_PATH)

# --- Flask Routes ---
@app.route('/')
def home():
    global dataframe_cleaned # Access the global DataFrame

    # Check if data failed to load during startup
    if not data_loaded_successfully:
        flash("Error: Could not load property data. Please check server logs.", "danger")
        # Render a basic template or redirect, showing an error
        return render_template('error.html', message="Could not load property data.")

    # Check if DataFrame is None or empty (could happen if CSV was empty)
    if dataframe_cleaned is None or dataframe_cleaned.empty:
        flash("Property data is currently unavailable or empty.", "warning")
        top_properties = []
        top_neighborhoods = {}
    else:
        try:
            # --- Calculate Top Properties ---
            # Ensure 'PRICE_DIFFERENCE' exists and is numeric before nlargest
            if 'PRICE_DIFFERENCE' in dataframe_cleaned.columns and pd.api.types.is_numeric_dtype(dataframe_cleaned['PRICE_DIFFERENCE']):
                # Select columns safely, ensuring they exist
                cols_to_select = [
                    'ADDRESS', 'SUBLOCALITY', 'PRICE', 'PREDICTED_PRICE', 'PRICE_DIFFERENCE',
                    'PROPERTYSQFT', 'BEDS', 'BATH'
                ]
                # Filter to only columns that actually exist in the dataframe
                available_cols = [col for col in cols_to_select if col in dataframe_cleaned.columns]

                # Get top 10, handling cases where there are fewer than 10 rows
                n_largest = min(10, len(dataframe_cleaned))
                if n_largest > 0:
                    top_properties_df = dataframe_cleaned.nlargest(n_largest, 'PRICE_DIFFERENCE')
                    top_properties = top_properties_df[available_cols].to_dict(orient='records')
                else:
                     top_properties = []
                     logging.warning("DataFrame is empty, cannot calculate top properties.")

            else:
                logging.warning("'PRICE_DIFFERENCE' column not found or not numeric. Cannot calculate top properties.")
                top_properties = []
                flash("Warning: Could not calculate top properties due to missing or invalid 'PRICE_DIFFERENCE' data.", "warning")


            # --- Calculate Top Neighborhoods ---
            # Ensure 'SUBLOCALITY' and 'PRICE_DIFFERENCE' exist
            if 'SUBLOCALITY' in dataframe_cleaned.columns and 'PRICE_DIFFERENCE' in dataframe_cleaned.columns and pd.api.types.is_numeric_dtype(dataframe_cleaned['PRICE_DIFFERENCE']):
                # Group by sublocality, calculate mean, handle potential NaNs, sort, take top 5
                neighborhood_means = dataframe_cleaned.dropna(subset=['SUBLOCALITY', 'PRICE_DIFFERENCE']) \
                                                   .groupby('SUBLOCALITY')['PRICE_DIFFERENCE'] \
                                                   .mean() \
                                                   .sort_values(ascending=False)
                n_top_neighborhoods = min(5, len(neighborhood_means))
                if n_top_neighborhoods > 0:
                     top_neighborhoods = neighborhood_means.head(n_top_neighborhoods).to_dict()
                else:
                    top_neighborhoods = {}
                    logging.warning("No valid neighborhoods found after grouping.")

            else:
                logging.warning("Columns 'SUBLOCALITY' or 'PRICE_DIFFERENCE' not found or invalid. Cannot calculate top neighborhoods.")
                top_neighborhoods = {}
                flash("Warning: Could not calculate top neighborhoods due to missing or invalid data.", "warning")

        except Exception as e:
            logging.error(f"An error occurred during data processing in the home route: {e}", exc_info=True)
            flash("An unexpected error occurred while processing data. Please check server logs.", "danger")
            # Fallback to empty data to prevent crashing the page
            top_properties = []
            top_neighborhoods = {}
            # Optionally, render an error page instead:
            # return render_template('error.html', message="Error processing property data.")

    # --- Render Template ---
    try:
        return render_template('index.html',
                               top_properties=top_properties,
                               top_neighborhoods=top_neighborhoods)
    except Exception as e: # Catches potential Jinja2 template errors
        logging.error(f"Error rendering template 'index.html': {e}", exc_info=True)
        # Provide a fallback response or error page
        return "<h1>Error rendering page</h1><p>Could not load the template. Check server logs.</p>", 500


# --- Route for manually reloading data (optional) ---
@app.route('/reload-data')
def reload_data_route():
    global data_loaded_successfully
    logging.info("Attempting to manually reload data...")
    data_loaded_successfully = load_data(CSV_FILE_PATH)
    if data_loaded_successfully:
        flash("Data reloaded successfully!", "success")
    else:
        flash("Failed to reload data. Check server logs.", "danger")
    return redirect(url_for('home'))


# --- Main execution ---
if __name__ == '__main__':
    # IMPORTANT: Turn off debug mode for production deployment!
    # Use a proper WSGI server like Gunicorn or Waitress instead of Flask's dev server.
    # Example for production (requires installing waitress): waitress-serve --host 0.0.0.0 --port 5000 your_script_name:app
    is_debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true' # Default to True for dev
    logging.info(f"Starting Flask server in {'DEBUG' if is_debug_mode else 'PRODUCTION'} mode.")
    app.run(debug=is_debug_mode, host='0.0.0.0', port=5000) # Listen on all interfaces