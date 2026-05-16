import codecs
with codecs.open('app.py', 'r', 'utf-8') as f:
    content = f.read()

target = '        source_mode = st.radio(\n            "Fuente de códigos",\n            ["Pegar códigos", "Subir catálogo CSV/Excel", "Todas las series del metadato"],\n        )'
replacement = '        source_mode = st.radio(\n            "Fuente de códigos",\n            ["Pegar códigos", "Subir catálogo CSV/Excel", "Todas las series del metadato"],\n            index=2,\n        )'

target2 = '        source_mode = st.radio(\r\n            "Fuente de códigos",\r\n            ["Pegar códigos", "Subir catálogo CSV/Excel", "Todas las series del metadato"],\r\n        )'
replacement2 = '        source_mode = st.radio(\r\n            "Fuente de códigos",\r\n            ["Pegar códigos", "Subir catálogo CSV/Excel", "Todas las series del metadato"],\r\n            index=2,\r\n        )'

content = content.replace(target, replacement)
content = content.replace(target2, replacement2)

with codecs.open('app.py', 'w', 'utf-8') as f:
    f.write(content)
