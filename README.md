## Python Queue Network Simulator

### 1. Instale o suporte a ambientes virtuais (se ainda não tiver)
sudo apt update
sudo apt install python3-venv

### 2. Crie e ative o ambiente
python3 -m venv venv
source venv/bin/activate

### 3. Agora instale o PyYAML
pip install pyyaml

### 4. Rode o simulador
python simulator.py model.yml
