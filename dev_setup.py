import setuptools

with open("README.md", "r") as README:
    long_description = README.read()

setuptools.setup(
    name="je_auto_control_dev",
    version="0.0.33",
    author="JE-Chen",
    author_email="zenmailman@gmail.com",
    description="auto testing",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/JE-Chen/AutoControl",
    packages=setuptools.find_packages(),
    install_requires=[
        "je_open_cv",
        "pillow",
        "numpy",
        "pyobjc-core;platform_system=='Darwin'",
        "pyobjc;platform_system=='Darwin'",
        "python3-Xlib;platform_system=='Linux'"
    ],
    classifiers=[
        "Programming Language :: Python :: 3.7",
        "Development Status :: 2 - Pre-Alpha",
        "Environment :: Win32 (MS Windows)",
        "Environment :: MacOS X",
        "Environment :: X11 Applications",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent"
    ]
)

# python dev_setup.py sdist bdist_wheel
# python -m twine upload dist/*


