from setuptools import setup, find_packages

setup(
    name="clipvault",
    version="1.1.0",
    description="A modern clipboard history manager for Linux with phone sync",
    author="Your Name",
    license="GPL-3.0-or-later",
    packages=find_packages(),
    install_requires=[
        "websockets>=12.0",
        "qrcode[pil]>=7.4",
    ],
    entry_points={
        "console_scripts": [
            "clipvault=clipvault.main:main",
        ]
    },
    python_requires=">=3.10",
)
