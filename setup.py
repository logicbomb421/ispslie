from setuptools import setup, find_packages

APP_NAME = "ispslie"

with open(f"{APP_NAME}/_version.py", "r") as fd:
    exec(fd.read())

setup(
    name=APP_NAME,
    version=__version__,  # noqa: _version.py
    description="A constant speedtest utility desingned to track actual up/down internet speeds.",
    url="https://github.com/logicbomb421/ispslie",
    author="Michael Hill",
    author_email="mhill421@gmail.com",
    packages=find_packages(),
    include_package_data=True,
    install_requires=["speedtest-cli", "influxdb-client[ciso]", "psutil", "requests"],
    extras_require={"develop": ["black", "jedi", "flake8"]},
)
