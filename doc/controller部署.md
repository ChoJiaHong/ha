sudo mkdir -p /arha 
sudo mkdir -p /arha/data 
sudo mkdir -p /arha/logs 
sudo cp ./logs/* /arha/logs/ 
sudo cp ./information/* /arha/data/ 

chmod +x controller_install.sh 

./controller_install.sh 