from setuptools import setup, find_packages
import os


# note that to activate the scripts as terminal commands, 
# python setup.py develop
# source ~/.(your shell script)

# Use Semantic Versioning, http://semver.org/

version_info = (0, 1, 0, '')
__version__ = '%d.%d.%d%s' % version_info


setup(name='EKG_Monitor',
      version=__version__,
      description='Monitor EKG with Olmex device',
      url='http://github.com/pbmanis/EKGMonitor',
      author='Paul B. Manis',
      author_email='pmanis@med.unc.edu',
      license='MIT',
      packages=find_packages(include=['src*']),
      python_requires='>=3.11.1',

      zip_safe=False,
      entry_points={
          'console_scripts': [

               ],
          'gui_scripts': [
                # 'mapevent_analyzer=nf107.mapevent_analyzer:main',
          ],
      },
      classifiers = [
             "Programming Language :: Python :: 3.11+",
             "Development Status ::  Beta",
             "Environment :: Console",
             "Intended Audience :: Manis Lab",
             "License :: MIT",
             "Operating System :: OS Independent",
             "Topic :: Software Development :: Tools :: Python Modules",
             "Topic :: Data Processing :: Neuroscience",
             ],
    )
