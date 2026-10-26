# V1 model loader

`__init__.py` implements inference for the trained CodeBERT + XGBoost V1 model. It loads model
files from the registry artifact root at `model_artifacts/v1/`; maintainers publish those files in
the `shield-v1.zip` asset on GitHub Release tag `v1`. Teammates use
`python -m shield_core.models.install --tag v1` to download and verify the bundle.

The XGBoost models and calibration data are packaged in the release bundle. CodeBERT's pretrained
weights are fetched or loaded from the local Hugging Face cache at inference time.
