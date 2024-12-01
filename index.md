Use this code to run in dv mode docker!!

docker build -f dev.dockerfile -t python-executor-dev .; `docker run --rm -it ` -v ${PWD}:/app ` -p 8000:8000` python-executor-dev
