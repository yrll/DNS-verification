#!/bin/bash


cargo build --release

# Copy the binary to the current directory
cp target/release/$(basename $(pwd)) $(pwd)
cp target/release/$(basename $(pwd)) $(pwd)/../temp_result