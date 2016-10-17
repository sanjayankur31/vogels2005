#!/usr/bin/env python3
"""
Signal Propagation and Logic Gating in Networks of Integrate-and-Fire Neurons.

File: vogels2005.py

Copyright 2016 Ankur Sinha
Author: Ankur Sinha <sanjay DOT ankur AT gmail DOT com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

from __future__ import print_function
import sys
sys.argv.append('--quiet')
import nest
import numpy
import math
import random


# see the aif source for symbol definitions
self.neuronDict = {'V_m': -60.,
                    't_ref': 5.0, 'V_reset': -60.,
                    'V_th': -50., 'C_m': 200.,
                    'E_L': -60., 'g_L': 10.,
                    'E_ex': 0., 'E_in': -80.,
                    'tau_syn_ex': 5., 'tau_syn_in': 10.}
# Set up TIF neurons
# Setting up two models because then it makes it easier for me to get
# them when I need to set up patterns
nest.CopyModel("iaf_cond_exp", "tif_neuronE")
nest.SetDefaults("tif_neuronE", self.neuronDict)
nest.CopyModel("iaf_cond_exp", "tif_neuronI")
nest.SetDefaults("tif_neuronI", self.neuronDict)

self.neuronsE = nest.Create('tif_neuronE', 8000)
self.neuronsI = nest.Create('tif_neuronI', 2000)
self.poissonExtE = nest.Create('poisson_generator',
                                self.populations['Poisson'],
                                params=self.poissonExtDict)
self.poissonExtI = nest.Create('poisson_generator',
                                self.populations['Poisson'],
                                params=self.poissonExtDict)
