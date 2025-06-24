import logging
import html2text
import os
import uuid
from datetime import datetime
from bs4 import BeautifulSoup
from aia_utils.logs_cfg import config_logger
from aia_utils import AiaHttpClient

class HTMLExtractor:
    def __init__(self):
        config_logger()
        self.logger = logging.getLogger(__name__)
        self.http_client = AiaHttpClient()

    def get_wahapedia_content(self, url: str, max_length: int = 32000) -> str:
        # Obtener el HTML
        response = self.http_client.get(url)
        if response.status_code == 200:
            html_content = response.text  # Usar text en lugar de json()
            self.logger.debug(f"HTML obtenido correctamente. Longitud: {len(html_content)}")
        else:
            self.logger.error(f"Error al obtener HTML. Status code: {response.status_code}")
            return f"Error al obtener HTML. Status code: {response.status_code}"
        
        # Procesar el HTML
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Eliminar elementos no deseados
        for element in soup.find_all(['script', 'style', 'meta', 'link', 'noscript', 'iframe']):
            element.decompose()
        
        # Eliminar atributos de datos y eventos
        for tag in soup.find_all(True):
            # Eliminar atributos de datos
            attrs_to_remove = [attr for attr in tag.attrs if attr.startswith('data-')]
            # Eliminar atributos de eventos
            attrs_to_remove.extend([attr for attr in tag.attrs if attr.startswith('on')])
            # Eliminar atributos de estilo
            attrs_to_remove.extend(['style'])
            
            # Mantener todas las clases
            if 'class' in attrs_to_remove:
                attrs_to_remove.remove('class')
            
            for attr in attrs_to_remove:
                del tag[attr]
        
        # Encontrar el div con la clase dsBannerWrap
        banner_div = soup.find('div', class_='dsBannerWrap')
        weapons_div = soup.find('table', class_='wTable')
        stratagems_div = soup.find('div', class_='dsAbility_noLine')
       
        if banner_div:
            self.logger.debug("Elemento principal encontrado")
            # Convertir el HTML a formato Markdown
            stats_content = self._html_to_markdown_html2text(banner_div)
            weapons_content = self._html_to_markdown_html2text(weapons_div)
            stratagems_content = self._html_to_markdown_html2text(stratagems_div)
            return stats_content, weapons_content, stratagems_content
        else:
            self.logger.warning("No se encontró el elemento principal")
            # Si no se encuentra, devolver el texto limpio
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            return text
    
    def _save_to_target_file(self, content: str, method_name: str):
        """Guarda el contenido en un archivo con nombre que incluye fecha y hora en la carpeta target/wh40k."""
        try:
            # Crear la carpeta target/wh40k si no existe
            target_dir = os.path.join("target", "wh40k")
            if not os.path.exists(target_dir):
                os.makedirs(target_dir)
            
            # Generar nombre de archivo con fecha, hora y elemento random
            timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
            random_id = str(uuid.uuid4())[:8]  # Primeros 8 caracteres del UUID
            filename = f"{timestamp}_{random_id}_{method_name}.md"
            filepath = os.path.join(target_dir, filename)
            
            # Guardar contenido
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self.logger.info(f"Contenido guardado en: {filepath}")
            
        except Exception as e:
            self.logger.error(f"Error al guardar archivo: {str(e)}")

    def _html_to_markdown(self, element):
        """Convierte elementos HTML específicos de Wahapedia a formato Markdown."""
        markdown_parts = []
        
        # Extraer título principal
        h2_header = element.find('div', class_='dsH2Header')
        if h2_header:
            title = h2_header.get_text().strip()
            if title:
                markdown_parts.append(f"# {title}")
        
        # Extraer estadísticas del perfil
        profile_wrap = element.find('div', class_='dsProfileWrap')
        if profile_wrap:
            markdown_parts.append("\n## Estadísticas del Perfil")
            
            # Buscar todas las estadísticas
            char_wraps = profile_wrap.find_all('div', class_='dsCharWrap')
            for char_wrap in char_wraps:
                char_name = char_wrap.find('div', class_='dsCharName')
                char_value = char_wrap.find('div', class_='dsCharValue')
                
                if char_name and char_value:
                    name = char_name.get_text().strip()
                    value = char_value.get_text().strip()
                    markdown_parts.append(f"- **{name}**: {value}")
        
        # Extraer información del modelo
        model_base = element.find('span', class_='dsModelBase2')
        if model_base:
            model_info = model_base.get_text().strip()
            if model_info:
                markdown_parts.append(f"\n**Tamaño del modelo**: {model_info}")
        
        # Extraer descripción del tooltip
        tooltip = element.find('div', class_='tooltip picLegend')
        if tooltip and tooltip.get('title'):
            description = tooltip.get('title')
            markdown_parts.append(f"\n## Descripción\n{description}")
        
        result = '\n'.join(markdown_parts)
        
        # Guardar en archivo
        self._save_to_target_file(result, "html_to_markdown")
        
        return result

    def _html_to_markdown_html2text(self, element):
        """Convierte elementos HTML a formato Markdown usando html2text."""
        try:
            # Configurar html2text
            h = html2text.HTML2Text()
            h.ignore_links = True  # Mantener enlaces
            h.body_width = 0  # Sin límite de ancho
            h.ignore_images = True  # Mantener imágenes
            h.ignore_emphasis = False  # Mantener énfasis (negrita, cursiva)
            h.ignore_tables = False  # Mantener tablas
            
            # Convertir el elemento HTML a string
            html_string = str(element)
            
            # Convertir a Markdown
            markdown_content = h.handle(html_string)
            
            result = markdown_content.strip()
            
            # Guardar en archivo
            self._save_to_target_file(result, "html_to_markdown_html2text")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error al convertir HTML a Markdown con html2text: {str(e)}")
            # Fallback: devolver el texto plano
            return None

    def explain_stats_natural_language(self, markdown_stats: str, aiamodels=None, max_length: int = 512) -> str:
        """
        Explica en lenguaje natural el significado de las estadísticas de Wahapedia a partir del markdown generado.
        """
        prompt = (
            "A continuación tienes estadísticas de una unidad de Warhammer 40k en formato Markdown. "
            "Explica en lenguaje natural el significado de cada estadística, considerando que: "
            "M es Movimiento, T es Resistencia, Sv es Salvación, Ld es Liderazgo, OC es Control de Objetivos. "
            "Hazlo de forma clara y didáctica para alguien que no conoce el juego.\n\n"
            f"Estadísticas extraídas:\n{markdown_stats}\n\n"
            "Responde en español, en un solo párrafo, explicando qué representa cada valor y cómo influye en el juego."
        )
        if aiamodels is None:
            from amanda_ia.services.ai_models import AIAModels
            aiamodels = AIAModels()
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "Explícalo en lenguaje natural."}
        ]
        respuesta = aiamodels._generate_response_internal(messages, max_length=max_length).strip()
        return respuesta