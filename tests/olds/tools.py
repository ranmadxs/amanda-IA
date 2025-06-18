from huggingface_hub import list_models
import datetime

get_company_info = {
  "type": "function",
  "function": {
    "name": "get_company_info",
    "description": "Información de la empresa extraída correctamente con todos los parámetros requeridos y con los tipos correctos.",
    "parameters": {
      "properties": {
        "name": {"title": "Name", "type": "string"},
        "investors": {
          "items": {"type": "string"},
          "title": "Investors",
          "type": "array"
        },
        "valuation": {"title": "Valuation", "type": "string"},
        "source": {"title": "Source", "type": "string"}
      },
      "required": ["investors", "name", "source", "valuation"],
      "type": "object"
    }
  }
}



def current_time() -> str:
    """Obtener la hora local actual."""
    return str(datetime.datetime.now())

def multiply(a: float, b: float) -> float:
    """
    Una función que multiplica dos números.
    
    Args:
        a: El primer número a multiplicar
        b: El segundo número a multiplicar
    """
    return a * b

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


class HFModelDownloadsTool:
    name = "model_download_counter"
    description = (
        "This is a tool that returns the most downloaded model of a given task on the Hugging Face Hub. "
        "It takes the name of the category (such as text-classification, depth-estimation, etc), and "
        "returns the name of the checkpoint."
    )

    def __call__(self, task: str):
        model = next(iter(list_models(filter=task, sort="downloads", direction=-1)))
        return model.id