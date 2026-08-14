# -*- coding: utf-8 -*-
"""
Cython compilation setup for iber_edonusum_uyumsoft core modules.

Usage (addon dizininden):
    python setup.py build_ext --inplace

Usage (üst dizinden):
    python iber_edonusum_uyumsoft/setup.py build_ext --inplace
"""
from setuptools import setup, Extension
from Cython.Build import cythonize
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

extensions = [
    Extension(
        'iber_edonusum_uyumsoft.core.uyumsoft_parser',
        ['core/uyumsoft_parser.py'],
        extra_compile_args=['-O3'],
    ),
]

setup(
    name='iber_edonusum_uyumsoft_core',
    version='19.0.1.5.0',
    package_dir={'iber_edonusum_uyumsoft': ''},
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            'language_level': '3',
            'boundscheck': False,
            'wraparound': False,
            'cdivision': True,
            'embedsignature': True,
        },
        annotate=True,
        nthreads=0,
    ),
    zip_safe=False,
)
