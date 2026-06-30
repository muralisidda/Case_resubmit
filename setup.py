from setuptools import setup, find_packages

setup(
    name='case_resubmit',
    version='1.0.0',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'Flask>=2.3.3',
        'SQLAlchemy>=2.0.20',
        'pyodbc>=4.0.39',
        'python-dotenv>=1.0.0',
        'Werkzeug>=2.3.7',
        'Jinja2>=3.1.2',
        'MarkupSafe>=2.1.3',
        'click>=8.1.7',
        'colorama>=0.4.6',
        'itsdangerous>=2.1.2',
    ],
    python_requires='>=3.8',
    description='ENV3 TIBCO Case Resubmit Web Application',
    author='AJ Bell',
)
