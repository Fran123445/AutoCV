# Mi experiencia

> Este archivo es la fuente de verdad del lado candidato: de acá salen
> `FactExperience`, `Project`, sus bridges y los rollups de skills. Es lo único
> del pipeline que ninguna re-corrida puede regenerar, así que guardalo fuera de
> `data/` y respaldalo.
>
> **Cómo llenarlo.** Copiá este archivo a la raíz del repo como `experience.md`
> (o apuntá `AUTOCV_EXPERIENCE_PATH` a donde lo tengas) y editalo.
>
> **Regla de parseo: toda línea que empieza con `>` es guía y se descarta.** El
> resto es contenido. Podés borrar las guías o dejarlas, da igual.
>
> **Los campos `clave: valor` se leen literal, la prosa la lee el modelo.** Por
> eso los campos tienen formato estricto y la prosa no tiene ninguno: escribí
> como hablás, en el idioma que quieras, sin bullets prolijos ni tercera
> persona. Canonicalizar contra las dims y arreglar la voz es trabajo del
> transform, no tuyo.
>
> **Vacío es válido.** Un campo que no sabés o no aplica se deja en blanco y
> entra como null. No inventes para llenar el hueco.

---

## Perfil

- birth_date:

> ISO 8601 (`YYYY-MM-DD`). Sólo esto, y sólo porque `FactUser` lo tiene. Si no
> lo querés en la base, dejalo vacío.

---

## Educación

> Un bloque por título. Copiá el bloque las veces que haga falta. Si no estudiaste
> formalmente, borrá la sección entera.

### Título 1

- degree: 
- institution: 
- start: 
- end: 

> `degree` sale de la lista del apéndice, verbatim. `end` vacío o `current` si
> está en curso.

### Título 2

- degree: 
- institution: 
- start: 
- end: 

---

## Experiencia

> Un bloque `### Trabajo N` por puesto. Copiá el bloque las veces que haga falta,
> del más reciente al más viejo. Un cambio de rol o de seniority dentro de la
> misma empresa es un bloque nuevo: la base modela el puesto, no el empleador.

### Trabajo 1

- company: 
- role: 
- seniority: 
- start: 
- end: 

> `role` y `seniority` salen verbatim de las listas del apéndice. Si ninguna
> opción encaja, escribí la tuya igual: el transform la marca como `unmatched` en
> vez de forzarla, y eso es una señal útil de que a los seeds les falta algo.
>
> Fechas: `YYYY-MM-DD`, o `YYYY-MM` si no te acordás el día (es lo normal).
> `end` vacío o `current` si seguís ahí.

#### Día a día

> Qué hacías realmente, no lo que decía el contrato. Tres o cuatro oraciones
> alcanzan. Sirve nombrar:
>
> - de qué eras dueño de punta a punta
> - con qué stack, y qué parte del stack tocabas vos
> - con quién trabajabas (equipo, tamaño, si liderabas a alguien)
> - qué tipo de problema aparecía una y otra vez
>
> Escribí las tecnologías con el nombre que usás al hablar. `postgres`, `postgre`
> y `PostgreSQL` resuelven todas a lo mismo; los alias están en los seeds.



#### Proyectos

> Acá está el 80% del valor del archivo. Un proyecto es una iniciativa concreta
> con principio y fin, no una responsabilidad continua: "migré el reporting de
> Excel a un warehouse" es un proyecto, "mantenía los reportes" es día a día.
>
> Dos o tres por trabajo, los que mejor te representen. Uno contado en detalle
> pesa más que cinco enumerados.
>
> Un bloque `##### <nombre>` por proyecto. El nombre es tuyo y para tu uso; no
> entra a la base, así que puede ser interno o inventado.

##### Proyecto 1

> Contestá estas cuatro. En prosa corrida, no como formulario: son la guía de lo
> que no hay que dejarse afuera, no campos.
>
> 1. **¿Qué problema resolvía?** Qué estaba roto, lento, manual o ausente antes.
> 2. **¿Qué construiste vos, específicamente?** La parte tuya, no la del equipo.
>    Si el proyecto era de diez personas, decí cuál de las diez partes era tuya.
> 3. **¿Con qué?** Lenguajes, frameworks, bases, servicios, herramientas. Nombrá
>    también las decisiones: por qué esa base y no otra, si es que decidiste vos.
> 4. **¿En qué terminó?** Números si los tenés (cuánto más rápido, cuántos
>    usuarios, cuánto ahorró). Si no los tenés, decilo cualitativo — un número
>    inventado es peor que ninguno, y en una entrevista se cae solo.



##### Proyecto 2



---

### Trabajo 2

- company: 
- role: 
- seniority: 
- start: 
- end: 

#### Día a día



#### Proyectos

##### Proyecto 1



---

## Proyectos personales

> Sólo los que **no** están en un repo que el ETL de projects ya escanea. Los que
> sí, entran solos con su `source_path` y contarlos acá los duplica.
>
> Mismo formato que los de arriba: nombre, y las cuatro preguntas en prosa.

### Proyecto 1



---

## Skills

> Rollup a `UserTechnologies` / `UserConcepts`. Sirve para dos cosas que la prosa
> sola no da: **profundidad** (la prosa dice que tocaste Kafka, no si sabés
> Kafka) y **cobertura** (lo que sabés y no llegó a aparecer en ningún trabajo).
>
> Formato: `nombre: N`, con N de 1 a 5. Sin número también sirve — entra con
> proficiency null, que es mejor que un número tirado al azar.
>
> Escala, para que 3 signifique lo mismo en todas las filas:
>
> | N | Qué significa |
> |---|---|
> | 1 | Lo toqué. Sé qué es y leo código que lo usa. |
> | 2 | Lo usé con supervisión o con la documentación abierta al lado. |
> | 3 | Autónomo en lo habitual. Me trabo en lo raro. |
> | 4 | Sólido. Reviso el código de otros y sé dónde están los filos. |
> | 5 | Referente. Me preguntan a mí, y sé por qué la herramienta es como es. |
>
> No hace falta que coincida con la prosa: acá podés poner algo que aprendiste
> por fuera del trabajo. Lo que sí conviene es no contradecirla — si un proyecto
> entero fue en Spark, Spark en 1 va a leerse raro.

### Tecnologías

- 
- 
- 

### Conceptos

> Lo no-tecnología: prácticas, arquitecturas, dominios, metodologías, y también
> las blandas si te importan (`mentoring`, `stakeholder management`). Van con la
> misma escala.

- 
- 
- 

---

## Apéndice — listas cerradas

> Estas tres listas salen de `seeds/`. Copiá el valor tal cual. Tecnologías y
> conceptos **no** están acá a propósito: son 768 y 441, no se eligen de una
> lista, se escriben como salgan y el transform los resuelve.

### `role`

> Dev: `backend dev` · `frontend dev` · `full stack dev` · `mobile dev` ·
> `software dev` · `embedded dev` · `game dev`
>
> Datos: `data engineer` · `analytics engineer` · `data scientist` ·
> `data analyst` · `bi dev` · `bi analyst` · `etl developer` · `data architect` ·
> `dba`
>
> IA/ML: `ml engineer` · `mlops engineer` · `ai engineer`
>
> Infra: `devops engineer` · `sre` · `cloud engineer` · `platform engineer` ·
> `security engineer`
>
> Otros: `qa engineer` · `systems analyst` · `business analyst` ·
> `functional analyst` · `solutions architect` · `software architect` ·
> `support engineer` · `rpa developer`

### `seniority`

> `trainee` · `junior` · `ssr` · `senior` · `lead`

### `degree`

> `computer science` · `systems engineering` · `software engineering` ·
> `computer engineering` · `informatics` · `information systems` ·
> `data science` · `electronics engineering` ·
> `telecommunications engineering` · `industrial engineering` · `engineering` ·
> `mathematics` · `statistics` · `physics`
