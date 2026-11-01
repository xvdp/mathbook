
from setuptools import setup, find_packages
name = "mathbook"
def _set_version(version):
    with open('mathbook/version.py', 'w', encoding='utf8') as _fi:
        _fi.write("version='"+version+"'")
        return version
    
subs = find_packages(where=name)
packages = [name] + [f'{name}.{p}' for p in subs]

setup(
    name="mathbook",
    packages=packages,
    entry_points={
        'console_scripts': [
            'mathbook=mathbook.__main__:make_mathbook',
        ]},
    author='xvdp',
    license='MIT',
    install_requires=["nbclient", "ipykernel", "jupyter_client", "nbformat"],
    package_dir={name: name,},
    version=_set_version(version='0.0.1')
)
