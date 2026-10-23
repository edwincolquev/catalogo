
#actualizar requirements
pip freeze > requirements.txt


#instalar requirements
python -m pip install -r requirements.txt

#corremos el programa
streamlit run main.py --server.port 8501 --server.address 0.0.0.0

#DESCARGAR ARCHVOS A MAQUINA2
git clone https://github.com/TU_USUARIO/TU_REPOSITORIO.git
cd TU_REPOSITORIO

git config --global user.email "tu-email@ejemplo.com"
git config --global user.name "Tu Nombre"

git pull origin main   #Antes de empezar a trabajar en la Maquina 2, descarga lo que hiciste en la Maquina 1:



#SUBIR CAMBIOS A REPOSITORIO
#listar estado de los archivos
git status

#agregar todos los archivos
git add .

#describir cambios y confirmar
git commit -m "descripcion de lo que hiciste"

#subir cambios al repositorio
git push origin main

