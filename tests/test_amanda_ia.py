from amanda_ia import __version__
from transformers import AutoModelForCausalLM, AutoTokenizer
device = "cuda" # the device to load the model onto

#poetry run pytest tests/test_amanda_ia.py::test_version -s
def test_version():
    print(__version__)
    assert __version__ == '0.1.0'

#poetry run pytest tests/test_amanda_ia.py::test_ia -s
def test_ia():
    print("test_ia")
    # load the model and tokenizer
    #model = AutoModelForCausalLM.from_pretrained(
    #    "Qwen/Qwen2-7B-Instruct",
    #    torch_dtype="auto",
    #    device_map="auto"
    #)