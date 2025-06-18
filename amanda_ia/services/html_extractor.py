import logging
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
            
            # Guardar HTML original para debug
            try:
                with open('html_original_debug_2.html', 'w', encoding='utf-8') as f:
                    f.write(html_content)
                self.logger.debug("HTML original guardado en html_original_debug_2.html")
            except Exception as e:
                self.logger.error(f"Error al guardar HTML original: {str(e)}")
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
        if banner_div:
            self.logger.debug("Elemento principal encontrado")
            # Convertir el HTML a formato Markdown
            markdown_content = self._html_to_markdown(banner_div)
            return markdown_content
        else:
            self.logger.warning("No se encontró el elemento principal")
            # Si no se encuentra, devolver el texto limpio
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            return text
    
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
        
        return '\n'.join(markdown_parts)