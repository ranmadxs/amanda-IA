import logging
from bs4 import BeautifulSoup
from aia_utils.logs_cfg import config_logger
from aia_utils import AiaHttpClient

class HTMLExtractor:
    def __init__(self):
        config_logger()
        self.logger = logging.getLogger(__name__)
        self.http_client = AiaHttpClient()

    def get_html_content(self, url: str, max_length: int = 32000) -> str:
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
            # Devolver el HTML del div y su contenido
            return str(banner_div)
        else:
            self.logger.warning("No se encontró el elemento principal")
            # Si no se encuentra, devolver el texto limpio
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            return text

    def get_url_content(self, url: str, prompt: str = None, max_length: int = 32000) -> str:
        """
        Obtiene el contenido de una URL y lo procesa con el modelo de IA si se proporciona un prompt.
        
        Args:
            url: La URL a procesar
            prompt: El prompt para extraer información específica
            max_length: Longitud máxima del contenido
            
        Returns:
            str: El contenido procesado o el HTML original
        """
        try:
            # Obtener el HTML original
            html_content = self.get_html_content(url, max_length)
            
            return html_content
            
        except Exception as e:
            self.logger.error(f"Error al procesar la URL {url}: {str(e)}")
            return f"Error inesperado al procesar la URL {url}: {str(e)}"