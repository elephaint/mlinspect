"""
An example pipeline
"""
import os
import warnings

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from tensorflow.keras.wrappers.scikit_learn import KerasClassifier
from example_pipelines.healthcare.healthcare_utils import MyW2VTransformer, create_model
from mlinspect.utils import get_project_root
from datawig import SimpleImputer as DatawigSimpleImputer


# FutureWarning: Given feature/column names or counts do not match the ones for the data given during fit
warnings.filterwarnings('ignore')

COUNTIES_OF_INTEREST = ['county2', 'county3']

# load input data sources (data generated with https://www.mockaroo.com as a single file and then split into two)
patients = pd.read_csv(os.path.join(str(get_project_root()), "example_pipelines", "healthcare",
                                    "healthcare_patients.csv"), na_values='?')
histories = pd.read_csv(os.path.join(str(get_project_root()), "example_pipelines", "healthcare",
                                     "healthcare_histories.csv"), na_values='?')

# combine input data into a single table
data = patients.merge(histories, on=['ssn'])

# compute mean complications per age group, append as column
complications = data.groupby('age_group').agg(mean_complications=('complications', 'mean'))

data = data.merge(complications, on=['age_group'])

# target variable: people with a high number of complications
data['label'] = data['complications'] > 1.2 * data['mean_complications']

# project data to a subset of attributes
data = data[['smoker', 'last_name', 'county', 'num_children', 'race', 'income', 'label']]

# imputing
smoker_imputer = DatawigSimpleImputer(
    input_columns=['county', 'num_children', 'income'],
    output_column='smoker',
    output_path='imputer_model'
)
smoker_imputer.fit(train_df=data, num_epochs=5)
data = smoker_imputer.predict(data)
data["smoker"] = data["smoker_imputed"]

race_imputer = DatawigSimpleImputer(
    input_columns=['county', 'num_children', 'income'],
    output_column='race',
    output_path='imputer_model'
)
race_imputer.fit(train_df=data, num_epochs=5)
data = race_imputer.predict(data)
data["race"] = data["race_imputed"]

county_imputer = DatawigSimpleImputer(
    input_columns=['race', 'num_children', 'income'],
    output_column='county',
    output_path='imputer_model'
)
county_imputer.fit(train_df=data, num_epochs=5)
data = county_imputer.predict(data)
data["county"] = data["county_imputed"]

data = data[['smoker', 'last_name', 'county', 'num_children', 'race', 'income', 'label']]

# filter data
data = data[data['county'].isin(COUNTIES_OF_INTEREST)]

# define the feature encoding of the data
featurisation = ColumnTransformer(transformers=[
    ("impute_and_one_hot_encode", OneHotEncoder(sparse=False, handle_unknown='ignore'), ['smoker', 'county', 'race']),
    ('word2vec', MyW2VTransformer(min_count=2), ['last_name']),
    ('numeric', StandardScaler(), ['num_children', 'income'])
])

# define the training pipeline for the model
neural_net = KerasClassifier(build_fn=create_model, epochs=10, batch_size=1, verbose=0, input_dim=108)
pipeline = Pipeline([
    ('features', featurisation),
    ('learner', neural_net)])

# train-test split
train_data, test_data = train_test_split(data, random_state=0)
# model training
model = pipeline.fit(train_data, train_data['label'])
# model evaluation
print(model.score(test_data, test_data['label']))
