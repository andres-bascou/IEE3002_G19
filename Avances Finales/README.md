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

## Instancias y Datos de Entrada

Para el análisis y simulación, se obtuvieron datos reales representativos para la generación y la demanda.

### Perfiles de Irradiancia Solar (PV)
Los perfiles de generación fotovoltaica provienen de la región de Calama, obtenidos a través del [Explorador de Energía Solar](https://solar.minenergia.cl/fotovoltaico) del Ministerio de Energía de Chile.
* **Nombre del sitio:** S1
* **Latitud:** -22.329551967431687
* **Longitud:** -68.93036941418038
* **Altura:** 2645.0 m.s.n.m.

Se generaron perfiles promedio para todos los meses del año y un promedio general para obtener un perfil típico. Esto permite que el código sea probado bajo condiciones estacionales específicas (ej. un mes en particular) o con un enfoque de planificación anual general.

### Perfiles de Carga (Demanda)
Las curvas de demanda se obtuvieron de los registros del Coordinador Eléctrico Nacional (SEN) de Chile, correspondientes al **31 de julio de 2026**. Estos perfiles fueron normalizados y clasificados según el tipo de consumo en los nodos del sistema:
1. Clientes Regulados.
2. Pequeñas Empresas.
3. Grandes Empresas.

## Referencias

[1] S. Landl, K. Harald. "Mitigating Overvoltage in Power Grids with Photovoltaic Systems by Energy Storage," *Environmental and Climate Technologies*, 470-483, Jul. 2022, doi: 10.2478/rtuect-2022-0036.

[2] R. Mishan, X. Fu, C. Hingu, M. Ben-Idris, "Impacts of Inertia and Photovoltaic Integration on Existing and Proposed Power System Transient Stability Parameters," *Energies*, 18, no. 11: 2915, June, 2025, doi: 10.3390/en18112915.

[3] S. Kulkarni, K. Duan, G. Pang, A. Bhatti, "Recent advancements and perspectives in lithium-ion battery technology," *Energy Strategy Reviews*, vol. 64, Mar. 2026.

[4] J. Blanco-Solano, D. J. Chacón Molina, and D. L. Chaustre Cárdenas, "Enhanced optimization-based PV hosting capacity method for improved planning of real distribution networks," *Electricity*, vol. 7, no. 1, Art. no. 12, Feb. 2026, doi: 10.3390/electricity7010012.

[5] U. Datta, A. Kalam, J. Shi, "Smart control of BESS in PV integrated EV charging station for reducing transformer overloading and providing battery-to-grid service," *Journal of Energy Storage*, vol. 28, Apr. 2020, doi: 10.1016/j.est.2020.101224.

[6] R. A. Jabr, "Radial distribution load flow using conic programming," *IEEE Trans. Power Syst.*, vol. 21, no. 3, pp. 1458--1459, Aug. 2006, doi: 10.1109/TPWRS.2006.879214.

[7] M. Farivar and S. H. Low, "Branch flow model: Relaxations and convexification," in *Proc. 51st IEEE Conf. Decision Control (CDC)*, Maui, HI, USA, Dec. 2012, pp. 3672--3679, doi: 10.1109/CDC.2012.6425823.

[8] N. Zheng, J. Jaworski, and B. Xu, "Arbitraging variable efficiency energy storage using analytical stochastic dynamic programming," *IEEE Trans. Power Syst.*, vol. 37, no. 6, pp. 4785--4795, Nov. 2022, doi: 10.1109/TPWRS.2022.3154353.

[9] M. Moradi-Sepahvand and T. Amraee, "Hybrid AC/DC transmission expansion planning considering HVAC to HVDC conversion under renewable penetration," *IEEE Trans. Power Syst.*, vol. 38, no. 5, pp. 4112--4123, Sep. 2023, doi: 10.1109/TPWRS.2022.3218579.

[10] X. Dong, C. Liu, J. Li, Q. Zhu, Y. Wang, J. Zhu, "Assessment of Distributed PV Hosting Capacity in Distribution Areas Based on Operating Region Analysis," *Algorithms*, vol 19, no. 4: 320. doi: 10.3390/a19040320.

[11] C. Bustos, E. Sauma, S. de la Torre, J. A. Aguado, J. Contreras, and D. Pozo, "Energy storage and transmission expansion planning: Substitutes or complements?," *IET Gener. Transm. Distrib.*, vol. 12, no. 8, pp. 1738--1746, Apr. 2018, doi: 10.1049/iet-gtd.2017.0759.

[12] M. E. Baran and F. F. Wu, "Network reconfiguration in distribution systems for loss reduction and load balancing," *IEEE Trans. Power Del.*, vol. 4, no. 2, pp. 1401--1407, Apr. 1989, doi: 10.1109/61.25627.

