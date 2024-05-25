"""
AI Plant Care System for Raspberry Pi (Autonomous Watering)

This script collects sensor data from various environmental sensors and logs it to a CSV file for AI training.

Author: Tommaso Bacci
"""
import json
import time
import csv
from datetime import datetime, timedelta
import sensors
from pump import Pump
import pandas as pd
import numpy as np
from utils import printlog
import tensorflow as tf
from tensorflow.keras.models import load_model


# Global variables
csv_filename = "plant_data.csv"
training_stats_filename = 'training_stats.json'
headers = ["date", "time", "soil_moisture_percent", "lux", "temperature", "humidity"] 
sensor_manager = sensors.SensorManager()
pump = Pump(23)
# model = load_model('soil_moisture_prediction_1dcnn.h5')

# Constants
MAX_RETRY = 3
RETRY_WAIT = 3


def get_data():
    try:
        global headers

        # Date and time
        now = datetime.now()

        date = now.strftime("%d/%m/%Y")
        time = now.strftime("%H:%M:%S")

        # Common Sensor Readings
        lux = sensor_manager.get_light_reading()
        humidity, temperature = sensor_manager.get_air_reading()
        
        # Individual Soil Moisture Readings + watering
        soil_moisture_percent = sensor_manager.get_soil_readings()
        printlog(f"\nSoil Moisture Average %: {soil_moisture_percent}")
        
        # Set Data
        data = [date, time, soil_moisture_percent, lux, temperature, humidity]
        # Return Data
        printlog("Packing OK!")
        return dict(zip(headers, data))

    except Exception as e:
        printlog(f"Error reading sensors: {e}")
        return None


def log_data(data, filename):
    printlog(f"\nLogging Data...")
    try:
        global headers
        # Open csv
        with open(filename, 'a', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=headers)
            # If file empty add headers
            if file.tell() == 0:
                writer.writeheader()
            # Write file
            writer.writerow(data)
        printlog(f"Logging {filename} OK!")
    except Exception as e:
        printlog(f"Error logging data: {e}")


def sleep_until_next_interval(interval_minutes):
    current_time = datetime.now()
    # calculate second to next interval xx:00 or xx:30
    minutes_to_next_interval = interval_minutes - (current_time.minute % interval_minutes)
    seconds_to_next_interval = (60 - current_time.second) + (minutes_to_next_interval - 1) * 60
    # Sleep until
    print(f"\nNext interval in {seconds_to_next_interval} seconds")
    time.sleep(seconds_to_next_interval)


def testHardware():
    sensor_manager.test()
    pump.test()


def get_last_48_rows(csv_filename):
    df = pd.read_csv(csv_filename).tail(48)
    return df


def read_json_file(json_filename):
    try:
        with open(json_filename, 'r') as file:
            data = json.load(file)
            train_means = data.get('train_means', [])
            train_stds = data.get('train_stds', [])
            return train_means, train_stds
    except Exception as e:
        print(f"Error reading JSON file: {e}")
        return [], []


def index_dates(df):
  # combine day and time to datetime column
  df['datetime'] = pd.to_datetime(df['date'] + ' ' + df['time'], format='%d/%m/%Y %H:%M:%S')

  # set deatetime to index
  df.set_index('datetime', inplace=True)

  df.drop(columns=['date', 'time'], inplace=True)

  return df


def add_model_columns(df):
    df['hour'] = df.index.hour
    df['minute'] = df.index.minute
    df['month'] = df.index.month

    # Combine hour and minute into a fractional hour representation
    df['hour_minute'] = df['hour'] + df['minute'] / 60.0

    # Time of day (hour and minute) features
    df['time_sin'] = np.sin(df['hour_minute'] * (2 * np.pi / 24))
    df['time_cos'] = np.cos(df['hour_minute'] * (2 * np.pi / 24))

    # Month features
    df['month_sin'] = np.sin((df['month'] - 1) * (2 * np.pi / 12))
    df['month_cos'] = np.cos((df['month'] - 1) * (2 * np.pi / 12))

    # Drop the temporary 'Hour', 'Minute', and 'Hour_Minute' columns if not needed for further analysis
    df.drop(columns=['hour', 'minute', 'hour_minute', 'month'], inplace=True)

    return df


def df_to_X(df, window_size=48):
    df_as_np = df.to_numpy()
    X = []
    for i in range(len(df_as_np) - window_size + 1):
        window = df_as_np[i:i + window_size]
        X.append(window)
    return np.array(X)


def preprocess(X, means, stds):
    # Apply normalization to specified columns
    X[:, :, 0] = (X[:, :, 0] - means[0]) / stds[0]  # Soil moisture percent
    X[:, :, 1] = (X[:, :, 1] - means[1]) / stds[1]  # Lux
    X[:, :, 2] = (X[:, :, 2] - means[2]) / stds[2]  # Temperature
    X[:, :, 3] = (X[:, :, 3] - means[3]) / stds[3]  # Humidity
    return X


def deprocess(preds, sm_mean, sm_std):
    preds = preds * sm_std + sm_mean  # Soil moisture percent
    return preds


if __name__ == "__main__":

    # Load model
    model = load_model('soil_moisture_1dcnn_pi.h5')
    # Load training stats
    train_means, train_stds = read_json_file(training_stats_filename) 

    # Start program
    while True:
        #Get time and date fro record
        now = datetime.now()
        day_now = now.strftime("%d/%m/%Y")
        time_now = now.strftime("%H:%M:%S")
        printlog(f"\n########## Date: {day_now} Time: {time_now}")
        try:
            # Getting  sensor data
            file_data = get_data()
            #Logging to CSV
            if file_data is not None:
                log_data(file_data, csv_filename)
            # Get last 24h
            last_data = get_last_48_rows(csv_filename)
            # Datetime index the data
            indexed_data = index_dates(last_data)            
            # Add time and month cise and cosine transformation
            model_df = add_model_columns(indexed_data)
            # Transform dataframe to array
            model_array = df_to_X(model_df)                       
            # normalise data with training statistics
            model_data = preprocess(model_array, train_means, train_stds)
            # Make prediction [[]]
            printlog("\nPredicting")
            prediction = model.predict(model_data)            
            # Clean data
            pred = round(prediction[0][0], 2)
            printlog(f"Predicted value: {pred}")
            # Pump logic
            if pred < 23:
                pump.water_plant()            
            # Set and sleep to next interval
            sleep_until_next_interval(30)
        except KeyboardInterrupt:
            break

