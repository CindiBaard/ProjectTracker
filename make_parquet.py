import pandas as pd

# Load the CSV using the semicolon separator
df = pd.read_csv("ProjectTrackerPP_Cleaned_NA.csv", sep=';', low_memory=False)

# Check the columns to make sure they are separate now
print("Columns found:", df.columns.tolist())

# Save the corrected version
df.to_parquet("ProjectTracker_Combined.parquet")

print("Success! The corrected Parquet file has been created.")