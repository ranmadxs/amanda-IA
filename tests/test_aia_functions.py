from amanda_ia import __version__
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch
import os
import json
from dotenv import load_dotenv
from amanda_ia.aia import AIAService
from datasets import Dataset
import datetime
from transformers import pipeline
from transformers import load_tool

## https://huggingface.co/docs/transformers/main/es/chat_templating


# Load environment variables
load_dotenv()

device = "cuda" if torch.cuda.is_available() else "cpu"

# poetry run pytest tests/test_aia_functions.py::test_load_tool -s
def test_load_tool():
    document_qa = load_tool("document-question-answering")
    print(f"- {document_qa.name}: {document_qa.description}")

# Test version
def test_version():
    print(__version__)
    assert __version__ == '0.1.0'

def get_current_temperature(location: str, unit: str) -> float:
    """
    Get the current temperature at a location.
    
    Args:
        location: The location to get the temperature for, in the format "City, Country"
        unit: The unit to return the temperature in. (choices: ["celsius", "fahrenheit"])
    Returns:
        The current temperature at the specified location in the specified units, as a float.
    """
    return 22.  # A real function should probably actually get the temperature!

def get_current_wind_speed(location: str) -> float:
    """
    Get the current wind speed in km/h at a given location.
    
    Args:
        location: The location to get the temperature for, in the format "City, Country"
    Returns:
        The current wind speed at the given location in km/h, as a float.
    """
    return 6.  # A real function should probably actually get the wind speed!



def current_time():
    """Get the current local time as a string."""
    return str(datetime.now())

def multiply(a: float, b: float):
    """
    A function that multiplies two numbers
    
    Args:
        a: The first number to multiply
        b: The second number to multiply
    """
    return a * b

#NOK  ------> responde super raro
# poetry run pytest tests/test_aia_functions.py::test_def2 -s
def test_def2():

    checkpoint = "HuggingFaceH4/zephyr-7b-beta"
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    model = AutoModelForCausalLM.from_pretrained(checkpoint, torch_dtype=torch.bfloat16, device_map="auto")
    #tools = [get_current_temperature, get_current_wind_speed]
    messages = [
        {"role": "system", "content": "You are a bot that responds to weather queries. You should reply with the unit used in the queried location."},
        {"role": "user", "content": "Can you give me the current time?"}
    ]

    # A simple function that takes no arguments
    current_time = {
        "type": "function", 
        "function": {
            "name": "current_time",
            "description": "Get the current local time as a string.",
            "parameters": {
            'type': 'object',
            'properties': {}
            }
        }
    }

    # A more complete function that takes two numerical arguments
    multiply = {
        "type": "function",
        "function": {
            "name": "multiply",
            "description": "A function that multiplies two numbers", 
            "parameters": {
            "type": "object", 
            "properties": {
                "a": {
                "type": "number",
                "description": "The first number to multiply"
                }, 
                "b": {
                "type": "number", "description": "The second number to multiply"
                }
            }, 
            "required": ["a", "b"]
            }
        }
    }
    messages = [
        {"role": "system", "content": "You are a bot that responds to time queries."},
        {"role": "user", "content": "Hey, what time is it?"}
    ]
    
    tools = [current_time, multiply]
    #tools = [get_current_temperature, get_current_wind_speed]
    inputs = tokenizer.apply_chat_template(messages, chat_template="tool_use", tools=tools, add_generation_prompt=True, return_dict=True, return_tensors="pt")
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    out = model.generate(**inputs, max_new_tokens=128)
    print(tokenizer.decode(out[0]))
    print("=============")
    print(tokenizer.decode(out[0][len(inputs["input_ids"][0]):]))
    #inputs = tokenizer.apply_chat_template(messages, chat_template="Python 3.11.6", tools=tools, add_generation_prompt=True, return_dict=True, return_tensors="pt")
    #out = model.generate(inputs, max_new_tokens=128)
    #print(tokenizer.decode(out[0]))

# poetry run pytest tests/test_aia_functions.py::test_functions -s
def test_functions():
    print("test_functions LOLAZO")
    model_path = "ibm-granite/granite-20b-functioncalling"
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    # drop device_map if running on CPU
    model = AutoModelForCausalLM.from_pretrained(model_path, device_map=device)
    model.eval()

    # define the user query and list of available functions
    query = "What's the current weather in New York?"
    functions = [
        {
            "name": "get_current_weather",
            "description": "Get the current weather",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA"
                    }
                },
                "required": ["location"]
            }
        },
        {
            "name": "get_stock_price",
            "description": "Retrieves the current stock price for a given ticker symbol. The ticker symbol must be a valid symbol for a publicly traded company on a major US stock exchange like NYSE or NASDAQ. The tool will return the latest trade price in USD. It should be used when the user asks about the current or most recent price of a specific stock. It will not provide any other information about the stock or company.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "The stock ticker symbol, e.g. AAPL for Apple Inc."
                    }
                },
                "required": ["ticker"]
            }
        }
    ]


    # serialize functions and define a payload to generate the input template
    payload = {
        "functions_str": [json.dumps(x) for x in functions],
        "query": query,
    }

    instruction = tokenizer.apply_chat_template(payload, tokenize=False, add_generation_prompt=True)

    # tokenize the text
    input_tokens = tokenizer(instruction, return_tensors="pt").to(device)

    # generate output tokens
    outputs = model.generate(**input_tokens, max_new_tokens=100)

    # decode output tokens into text
    outputs = tokenizer.batch_decode(outputs)

    # loop over the batch to print, in this example the batch size is 1
    for output in outputs:
        # Each function call in the output will be preceded by the token "<function_call>" followed by a 
        # json serialized function call of the format {"name": $function_name$, "arguments" {$arg_name$: $arg_val$}}
        # In this specific case, the output will be: <function_call> {"name": "get_current_weather", "arguments": {"location": "New York"}}
        print(output)    



#NOK  ----> responde raro
# poetry run pytest tests/test_aia_functions.py::test_def -s
def test_def():
    checkpoint = "HuggingFaceH4/zephyr-7b-beta"
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    model = AutoModelForCausalLM.from_pretrained(
        checkpoint,
        torch_dtype="auto",
        device_map="auto"
    )
    tools = [get_current_temperature, get_current_wind_speed]
    messages = [
        {"role": "system", "content": "You are a bot that responds to weather queries. You should reply with the unit used in the queried location."},
        {"role": "user", "content": "Hey, what's the temperature in Paris right now?"}
    ]
    inputs = tokenizer.apply_chat_template(messages, chat_template="tool_use", tools=tools, add_generation_prompt=True, return_dict=True, return_tensors="pt")
    inputs = {k: v.to(model.device) for k, v in inputs.items()}
    out = model.generate(**inputs, max_new_tokens=128)
    print(tokenizer.decode(out[0]))
    print("=============")
    print(tokenizer.decode(out[0][len(inputs["input_ids"][0]):]))


#OK
# poetry run pytest tests/test_aia_functions.py::test_tools -s
def test_tools():
    print("test_tools")
    # Create a list of tools to test
    checkpoint = "HuggingFaceH4/zephyr-7b-beta"
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    model = AutoModelForCausalLM.from_pretrained(checkpoint)

    messages = [
        {"role": "user", "content": "Hello, how are you?"},
        {"role": "assistant", "content": "I'm doing great. How can I help you today?"},
        {"role": "user", "content": "I'd like to show off how chat templating works!"}
    ]
    
    tokenized_chat = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True, return_tensors="pt")
    print(tokenizer.decode(tokenized_chat[0]))
    print("=============================================")

    outputs = model.generate(tokenized_chat, max_new_tokens=128) 
    print(tokenizer.decode(outputs[0]))
