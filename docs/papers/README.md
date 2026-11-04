# Papers citados en el proyecto

Los PDF de esta carpeta **no se suben al repositorio** (están en `.gitignore`), por derechos de autor y por tamaño. Cada integrante debe descargarlos y guardarlos aquí con el nombre indicado, para que los scripts, los agentes y el resto del equipo los encuentren en la misma ruta.

- **Convención de nombre:** `NN_primer-autor_año.pdf` (NN = número de la referencia en el informe).
- **Papers de pago:** se pueden descargar con la cuenta UC a través de la Biblioteca UC (acceso remoto).
- **Texto para buscar:** `pdftotext -layout docs/papers/04_blanco-solano_2026.pdf -` permite buscar dentro de un paper desde la terminal.

## Referencias del informe

| Ref. | Archivo esperado | Referencia | DOI | Acceso | Uso en el proyecto |
|---|---|---|---|---|---|
| [1] | `01_landl_2022.pdf` | Landl & Harald, *Environ. Climate Technol.*, 2022 | [10.2478/rtuect-2022-0036](https://doi.org/10.2478/rtuect-2022-0036) | Abierto | Sobretensiones por PV y mitigación con BESS (motivación) |
| [2] | `02_mishan_2025.pdf` | Mishan et al., *Energies* 18(11), 2025 | [10.3390/en18112915](https://doi.org/10.3390/en18112915) | Abierto (MDPI) | Impacto de la integración PV en la estabilidad (motivación) |
| [3] | `03_kulkarni_2026.pdf` | Kulkarni et al., *Energy Strategy Rev.* 64, 2026 | — | Abierto | Estado del arte de baterías de ion-litio (motivación) |
| **[4]** | **`04_blanco-solano_2026.pdf`** | **Blanco-Solano et al., *Electricity* 7(1), 2026** | [10.3390/electricity7010012](https://doi.org/10.3390/electricity7010012) | Abierto (MDPI) | **Paper base:** formulación de HC, red IEEE 33-bus (Sec. 4.1), I_max = 300 A, **Tabla 1 a replicar en la Etapa 2** |
| [5] | `05_datta_2020.pdf` | Datta et al., *J. Energy Storage* 28, 2020 | [10.1016/j.est.2020.101224](https://doi.org/10.1016/j.est.2020.101224) | Pago | Operación de BESS con PV y carga de vehículos eléctricos |
| **[6]** | **`06_jabr_2006.pdf`** | **Jabr, *IEEE Trans. Power Syst.* 21(3), 2006** | [10.1109/TPWRS.2006.879214](https://doi.org/10.1109/TPWRS.2006.879214) | Pago | **Relajación cónica del flujo de potencia radial** |
| **[7]** | **`07_farivar_2012.pdf`** | **Farivar & Low, *IEEE CDC*, 2012** | [10.1109/CDC.2012.6425823](https://doi.org/10.1109/CDC.2012.6425823) | Pago; hay preprint en arXiv | **Branch Flow Model y condiciones de exactitud de la relajación** |
| [8] | `08_zheng_2022.pdf` | Zheng et al., *IEEE Trans. Power Syst.* 37(6), 2022 | [10.1109/TPWRS.2022.3154353](https://doi.org/10.1109/TPWRS.2022.3154353) | Pago; posible preprint en arXiv | Arbitraje y degradación de almacenamiento |
| [9] | `09_moradi-sepahvand_2023.pdf` | Moradi-Sepahvand & Amraee, *IEEE Trans. Power Syst.* 38(5), 2023 | [10.1109/TPWRS.2022.3218579](https://doi.org/10.1109/TPWRS.2022.3218579) | Pago | Planificación conjunta de líneas y BESS |
| [10] | `10_dong_2026.pdf` | Dong et al., *Algorithms* 19(4):320 | [10.3390/a19040320](https://doi.org/10.3390/a19040320) | Abierto (MDPI) | HC con BESS y reguladores de tensión (Monte Carlo + OpenDSS) |
| [11] | `11_bustos_2018.pdf` | Bustos et al., *IET Gener. Transm. Distrib.* 12(8), 2018 | [10.1049/iet-gtd.2017.0759](https://doi.org/10.1049/iet-gtd.2017.0759) | Pago | Almacenamiento y expansión de transmisión |
| **[12]** | **`12_baran_1989.pdf`** | **Baran & Wu, *IEEE Trans. Power Del.* 4(2), 1989** | [10.1109/61.25627](https://doi.org/10.1109/61.25627) | Pago | **Datos originales de la red IEEE 33-bus** |

En negrita, las referencias de las que depende directamente el modelo; conviene tenerlas primero.

## Fuentes de parámetros del modelo (`modelo/misocp_hc_bess.py`, `HCConfig`)

| Ref. | Archivo esperado | Fuente | Parámetro |
|---|---|---|---|
| [R3] | (página web) | [Terralink, guía BESS](https://www.terralink.cl/aprende/almacenamiento-energia-solar-bess-guia-empresas-chile) | η_ch = η_dis = 0.95 |
| [R4] | `R4_tfm-unizar_2026.pdf` | [TFM-2026-006, Universidad de Zaragoza](https://zaguan.unizar.es/record/170538/files/TAZ-TFM-2026-006.pdf) | c_deg = 0.019 |
| [R5] | (página web) | [National Battery Authority](https://nationalbatteryauthority.com/battery-energy-storage-systems-commercial/) | E_max = 100 kWh por BESS |
