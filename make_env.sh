set -e # force failure if anyting fails in script - ensuring completion
set -o errexit
ENVNAME="ekg_venv"
if [ -d $ENVNAME ]
then
    echo "Removing previous environment: $ENVNAME"
    set +e
    rsync -aR --remove-source-files $ENVNAME ~/.Trash/ || exit 1
    set -e
    rm -R $ENVNAME
else
    echo "No previous environment - ok to proceed"
fi
python3.11 -m venv $ENVNAME || exit 1
source $ENVNAME/bin/activate || exit 1

pip3 install --upgrade pip  # be sure pip is up to date in the new env.
pip3 install wheel  # seems to be missing (note singular)
# $PYTHONVER -m pip install install Cython==3.0.11
# # if requirements.txt is not present, create:
# # pip install pipreqs
# # pipreqs
#
pip3 install -r requirements.txt
source $ENVNAME/bin/activate
python --version
python setup.py develop
