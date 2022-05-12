# Copyright 2021 The HuggingFace Team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from os import mkdir, getenv
import requests
from os.path import exists, isdir
from pathlib import Path
from dotenv import load_dotenv
import threading
import pickle

import streamlit as st

from data_measurements import dataset_statistics, dataset_utils
from data_measurements import streamlit_utils as st_utils
from email_validator import validate_email, EmailNotValidError
from datasets import list_datasets

if Path(".env").is_file():
    load_dotenv(".env")

SERVER_URL = getenv("SERVER_URL")


logs = logging.getLogger(__name__)
logs.setLevel(logging.WARNING)
logs.propagate = False

if not logs.handlers:

    Path('./log_files').mkdir(exist_ok=True)

    # Logging info to log file
    file = logging.FileHandler("./log_files/app.log")
    fileformat = logging.Formatter("%(asctime)s:%(message)s")
    file.setLevel(logging.INFO)
    file.setFormatter(fileformat)

    # Logging debug messages to stream
    stream = logging.StreamHandler()
    streamformat = logging.Formatter("[data_measurements_tool] %(message)s")
    stream.setLevel(logging.WARNING)
    stream.setFormatter(streamformat)

    logs.addHandler(file)
    logs.addHandler(stream)

st.set_page_config(
    page_title="Demo to showcase dataset metrics",
    page_icon="https://huggingface.co/front/assets/huggingface_logo.svg",
    layout="wide",
    initial_sidebar_state="auto",
)

# colorblind-friendly colors
colors = [
    "#332288",
    "#117733",
    "#882255",
    "#AA4499",
    "#CC6677",
    "#44AA99",
    "#DDCC77",
    "#88CCEE",
]

CACHE_DIR = dataset_utils.CACHE_DIR
# String names we are using (not coming from the stored dataset).
OUR_TEXT_FIELD = dataset_utils.OUR_TEXT_FIELD
OUR_LABEL_FIELD = dataset_utils.OUR_LABEL_FIELD
TOKENIZED_FIELD = dataset_utils.TOKENIZED_FIELD
EMBEDDING_FIELD = dataset_utils.EMBEDDING_FIELD
LENGTH_FIELD = dataset_utils.LENGTH_FIELD
# TODO: Allow users to specify this.
_MIN_VOCAB_COUNT = 10
_SHOW_TOP_N_WORDS = 10


def load_or_prepare(ds_args, show_embeddings, use_cache=False):
    """
    Takes the dataset arguments from the GUI and uses them to load a dataset from the Hub or, if
    a cache for those arguments is available, to load it from the cache.
    Args:
        ds_args (dict): the dataset arguments defined via the streamlit app GUI
        show_embeddings (Bool): whether embeddings should we loaded and displayed for this dataset
        use_cache (Bool) : whether the cache is used by default or not
    Returns:
        dstats: the computed dataset statistics (from the dataset_statistics class)
    """
    if not isdir(CACHE_DIR):
        logs.warning("Creating cache")
        # We need to preprocess everything.
        # This should eventually all go into a prepare_dataset CLI
        mkdir(CACHE_DIR)
    if use_cache:
        logs.warning("Using cache")
    dstats = dataset_statistics.DatasetStatisticsCacheClass(CACHE_DIR, **ds_args, use_cache=use_cache)
    logs.warning("Loading dataset")
    dstats.load_or_prepare_dataset()
    logs.warning("Loading labels")
    dstats.load_or_prepare_labels()
    logs.warning("Loading text lengths")
    dstats.load_or_prepare_text_lengths()
    logs.warning("Loading duplicates")
    dstats.load_or_prepare_text_duplicates()
    logs.warning("Loading vocabulary")
    dstats.load_or_prepare_vocab()
    logs.warning("Loading general statistics...")
    dstats.load_or_prepare_general_stats()
    if show_embeddings:
        logs.warning("Loading Embeddings")
        dstats.load_or_prepare_embeddings()
    logs.warning("Loading nPMI")
    try:
        dstats.load_or_prepare_npmi()
    except:
        logs.warning("Missing a cache for npmi")
    logs.warning("Loading Zipf")
    dstats.load_or_prepare_zipf()
    return dstats

def load_or_prepare_widgets(ds_args, show_embeddings, use_cache=False):
    """
    Loader specifically for the widgets used in the app.
    Args:
        ds_args:
        show_embeddings:
        use_cache:

    Returns:

    """

    if use_cache:
        logs.warning("Using cache")
    if True:
    #try:
        dstats = dataset_statistics.DatasetStatisticsCacheClass(CACHE_DIR, **ds_args, use_cache=use_cache)
        # Don't recalculate; we're live
        dstats.set_deployment(True)
        # checks whether the cache_dir exists in deployment mode
        # creates cache_dir if not and if in development mode
        cache_dir_exists = dstats.check_cache_dir()
    #except:
    #    logs.warning("We're screwed")
    if cache_dir_exists:
        try:
            # We need to have the text_dset loaded for further load_or_prepare
            dstats.load_or_prepare_dataset()
        except:
            logs.warning("Missing a cache for load or prepare dataset")
        try:
            # Header widget
            dstats.load_or_prepare_dset_peek()
        except:
            logs.warning("Missing a cache for dset peek")
        try:
            # General stats widget
            dstats.load_or_prepare_general_stats()
        except:
            logs.warning("Missing a cache for general stats")
        try:
            # Labels widget
            dstats.load_or_prepare_labels()
        except:
            logs.warning("Missing a cache for prepare labels")
        try:
            # Text lengths widget
            dstats.load_or_prepare_text_lengths()
        except:
            logs.warning("Missing a cache for text lengths")
        if show_embeddings:
            try:
                # Embeddings widget
                dstats.load_or_prepare_embeddings()
            except:
                logs.warning("Missing a cache for embeddings")
        try:
            dstats.load_or_prepare_text_duplicates()
        except:
            logs.warning("Missing a cache for text duplicates")
        try:
            dstats.load_or_prepare_npmi()
        except:
            logs.warning("Missing a cache for npmi")
        try:
            dstats.load_or_prepare_zipf()
        except:
            logs.warning("Missing a cache for zipf")
    return dstats, cache_dir_exists

def show_column(dstats, ds_configs, show_embeddings, column_id):
    """
    Function for displaying the elements in the right column of the streamlit app.
    Args:
        ds_configs (dict): the dataset options in dictionary form
        show_embeddings (Bool): whether embeddings should we loaded and displayed for this dataset
        column_id (str): what column of the dataset the analysis is done on
    Returns:
        The function displays the information using the functions defined in the st_utils class.
    """
    # Note that at this point we assume we can use cache; default value is True.
    # start showing stuff
    title_str = f"### Showing{column_id}: {dstats.dset_name} - {dstats.dset_config} - {dstats.split_name} - {'-'.join(dstats.text_field)}"
    st.markdown(title_str)
    logs.info("showing header")
    st_utils.expander_header(dstats, ds_configs, column_id)
    logs.info("showing general stats")
    st_utils.expander_general_stats(dstats, column_id)
    st_utils.expander_label_distribution(dstats.fig_labels, column_id)
    st_utils.expander_text_lengths(dstats, column_id)
    st_utils.expander_text_duplicates(dstats, column_id)
    # Uses an interaction; handled a bit differently than other widgets.
    logs.info("showing npmi widget")
    st_utils.npmi_widget(dstats.npmi_stats, _MIN_VOCAB_COUNT, column_id)
    logs.info("showing zipf")
    st_utils.expander_zipf(dstats.z, dstats.zipf_fig, column_id)
    if show_embeddings:
        st_utils.expander_text_embeddings(
            dstats.text_dset,
            dstats.fig_tree,
            dstats.node_list,
            dstats.embeddings,
            OUR_TEXT_FIELD,
            column_id,
        )

def display_or_compute_data_measures(cache_exists, dstats, show_embeddings, dataset_args, ds_configs, column_id=""):
    if cache_exists:
        if dstats.complete:
            show_column(dstats, ds_configs, show_embeddings, column_id)
        else:
            st.markdown("Check back later for data measurement results!")
    else:
        email_input = st.empty()
        compute_button = st.empty()
        email = email_input.text_input("We are missing pre-computed data measures for this configuration. Enter your email. Our app will compute the measurements and email you when done!")
        compute = compute_button.button("Compute Measurements")

        try:
            # Validate.
            valid = validate_email(email)

            # Update with the normalized form.
            email = valid.email

        except EmailNotValidError as e:
            valid = False

        if valid:
            if compute:
                result = requests.post(SERVER_URL, data = dict({"email": email}, **dataset_args))
                email_input.empty()
                compute_button.empty()
                if result.text == "success":
                    st.text("Computing metrics! An email will be sent to you.\nThis could take a while if the dataset is big.")
                else:
                    st.text("Oh no, a problem happened while requesting the data measurements.")
        else:
            if email != "" or compute:
                st.text("Oh no, that email doesn't seem valid!")

@st.cache(ttl=3600)
def list_datasets_wrapper():
    return list_datasets()

def main():
    """ Sidebar description and selection """
    ds_names = list_datasets_wrapper()
    st.title("Data Measurements Tool")
    # Get the sidebar details
    st_utils.sidebar_header()
    # Set up naming, configs, and cache path.
    compare_mode = st.sidebar.checkbox("Comparison mode")

    # When not doing new development, use the cache.
    use_cache = True
    show_embeddings = st.sidebar.checkbox("Show text clusters")
    # List of datasets for which embeddings are hard to compute:

    if compare_mode:
        logs.warning("Using Comparison Mode")
        dataset_args_left, ds_configs_left = st_utils.sidebar_selection(ds_names, " A")
        dataset_args_right, ds_configs_right = st_utils.sidebar_selection(ds_names, " B")
        left_col, _, right_col = st.columns([10, 1, 10])
        dstats_left, cache_exists_left = load_or_prepare_widgets(
            dataset_args_left, show_embeddings, use_cache=use_cache
        )
        with left_col:
            display_or_compute_data_measures(cache_exists_left, dstats_left, show_embeddings, dataset_args_left, ds_configs_left, column_id=" A")
        dstats_right, cache_exists_right = load_or_prepare_widgets(
            dataset_args_right, show_embeddings, use_cache=use_cache
        )
        with right_col:
            display_or_compute_data_measures(cache_exists_right, dstats_right, show_embeddings, dataset_args_right, ds_configs_right, column_id=" B")
    else:
        logs.warning("Using Single Dataset Mode")
        dataset_args, ds_configs = st_utils.sidebar_selection(ds_names, "")
        dstats, cache_exists = load_or_prepare_widgets(dataset_args, show_embeddings, use_cache=use_cache)
        display_or_compute_data_measures(cache_exists, dstats, show_embeddings, dataset_args, ds_configs)


if __name__ == "__main__":
    main()
