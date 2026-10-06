# Análisis de Redes y Perfiles de Demanda/Generación PV (IEEE 33-Bus)

Este repositorio contiene los scripts de generación, validación y datos base para el modelado de la red de distribución IEEE de 33 barras, así como los perfiles de demanda y generación fotovoltaica asociados.

## Estructura del Proyecto

El repositorio está organizado de la siguiente manera:

* **Archivos en la Raíz:**
  * `comprobacion_perfiles.py` y `comprobacion_perfiles.png`: Script y visualización para la validación de los perfiles generados.[cite: 1]
  * `comprobaciones_cargas.py` y `comprobacion_red.py`: Scripts para verificar la consistencia técnica de las cargas y los parámetros topológicos de la red.[cite: 1]
  * `generacion_perfil_carga.py` y `generacion_perfil_pv.py`: Scripts encargados de procesar y generar los perfiles normalizados de consumo y generación.[cite: 1]
  * `generacion_red.py`: Script para el ensamblaje de la red eléctrica.[cite: 1]
  * `red_interactiva.html`: Mapa o visualización interactiva de la topología resultante.[cite: 1]
  * **Datos crudos:** Archivos base `.xlsx` de demandas (grandes empresas, pequeñas empresas, regulados) y el archivo de datos fotovoltaicos `DHC_PV_MX1701.csv`.[cite: 1]

* **Carpeta `data/`**:[cite: 1]
  * `main.py`: Script principal de orquestación (ubicado en esta carpeta).[cite: 1]
  * `grafico_resultados.py`: Script para la generación de gráficas a partir de resultados.[cite: 1]
  * `demand/`: Contiene los perfiles de demanda procesados (`demand_profiles_norm_mean.csv`, `demand_profiles_norm_peak.csv`, `demand_raw_aggregated_MW.csv`).[cite: 1]
  * `grid/`: Contiene la topología y parámetros de la red (`ieee33_branches.csv`, `ieee33_nodes.csv`).[cite: 1]
  * `pv_profiles/`: Perfiles solares separados por mes (`alpha_t_mes_01.csv` al `12.csv`), matriz anual (`alpha_t_mensual_anual.csv`), y gráficos de verificación (`verificacion_estacional.png`, `verificacion_heatmap.png`).[cite: 1]

* **Carpeta `results/`**:[cite: 1]
  * Archivos JSON con los registros de la optimización (ej. `hc_bess_results_m7_20261006_095447.json`).[cite: 1]
  * `figures/`: Dashboards interactivos y representaciones topológicas en formato `.html`.[cite: 1]

## Ejecución

1. Ejecuta los scripts de la serie `generacion_*.py` en la raíz para procesar los Excels y generar los CSVs limpios dentro de `data/`.
2. Utiliza la serie `comprobacion_*.py` para validar que no haya discrepancias matriciales ni errores en la topología.
3. Ingresa al directorio `data/` y ejecuta `main.py` para correr el proceso central.[cite: 1]
4. Los resultados se volcarán en la carpeta `results/` y pueden ser visualizados con `grafico_resultados.py`.[cite: 1]
