from .pair_classification import PairClassificationPipeline, MyPipeline
from transformers.pipelines import PIPELINE_REGISTRY, get_supported_tasks
from transformers import AutoModelForSequenceClassification, TFAutoModelForSequenceClassification
from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM
import torch


PIPELINE_REGISTRY.register_pipeline(
    "my-new-task",
    pipeline_class=PairClassificationPipeline,
    pt_model=AutoModelForSequenceClassification,
    tf_model=TFAutoModelForSequenceClassification,
)

# poetry run pytest tests/test_pipeline.py::test_pipe -s
def test_pipe():
    model = "mrm8488/bert-base-spanish-wwm-cased-finetuned-spa-squad2-es"
    #model = "Qwen/Qwen2-0.5B-Instruct"   <----- no funcia
    question_answerer = pipeline(task="question-answering", model=model)
    resp= question_answerer([{
        "question": "dime sólo tu apellido, responde sólo con 1 palabra",
        "context": "Mi nombre es Amanda Sánchez, soy una IA cochona y estoy aquí para ayudarte en lo que necesites."
        }, {
        "question": "¿puedes prender la bomba?. sólo dame el código",
        "context": "para encender la luz de mi cuarto debo responder el codigo 0098, para encender la bomba el codigo es 00199"
        }]
    )
    print(resp) 


# poetry run pytest tests/test_pipeline.py::test_pipe2 -s
def test_pipe2():
    print(get_supported_tasks())
    pipe = pipeline(task="my-new-task", model="Qwen/Qwen2-0.5B-Instruct", framework = "pt")
    resp = pipe("This is a test", "This is a")
    print(resp) 

#conversar es muy bueno
# poetry run pytest tests/test_pipeline.py::test_pipe3 -s
def test_pipe3():
    generator = pipeline("text-generation", model="Qwen/Qwen2-0.5B-Instruct")
    resp = generator([{"role": "user", "content": "La capital de Petorca es: La Ligua."},
        {"role": "user", "content": "¿Cuál es la capital de Petorca? Responde a lo más en 2 palabras."
         }],do_sample=False, max_new_tokens=2)
    print(resp)