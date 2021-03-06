#!/usr/bin/env python
"""
NEST implementation of Vogels et al. model.

File: Sinha2016.py

Copyright 2015 Ankur Sinha
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


class Sinha2016:

    """Simulations for my PhD 2016."""

    def __init__(self):
        """Initialise variables."""
        # default resolution in nest is 0.1ms. Using the same value
        # http://www.nest-simulator.org/scheduling-and-simulation-flow/
        self.dt = 0.1
        # time to stabilise network after pattern storage etc.
        self.stabilisation_time = 12000.  # seconds
        self.sp_recording_interval = 1000.  # seconds

        if self.stabilisation_time % self.sp_recording_interval != 0.0:
            self.sp_recording_interval = self.stabilisation_time/2.

        # structural plasticity bits
        # must be an integer
        self.sp_update_interval = 100  # ms
        # time recall stimulus is enabled for
        self.recall_time = 1000.  # ms
        # Number of patterns we store
        self.numpats = 0

        self.recall_ext_i = 3000.

        self.rank = nest.Rank()

        self.patterns = []
        self.neuronsStim = []
        self.recalls = []
        self.sdP = []
        self.sdR = []
        self.sdL = []
        self.sdB = []
        self.sdStim = []
        self.pattern_spike_count_file_names = []
        self.pattern_spike_count_files = []
        self.pattern_count = 0

        self.weightEE = 3.
        self.weightII = -30.
        self.weightEI = 3.
        self.weightExtE = 5.
        self.weightExtI = 5.

        random.seed(42)

    def __setup_neurons(self):
        """Setup neuron sets."""
        # populations
        self.populations = {'E': 8000, 'I': 2000, 'P': 800, 'R': 400,
                            'D': 200, 'STIM': 1000, 'Poisson': 1}
        # Growth curves
        # eta is the minimum calcium concentration
        # epsilon is the target mean calcium concentration
        # Excitatory synaptic elements of excitatory neurons
        self.growth_curve_axonal = {
            'growth_curve': "gaussian",
            'growth_rate': 0.0001,  # (elements/ms)
            'continuous': False,
            'eta': 0.4,
            'eps': 0.7,
        }

        # Inhibitory synaptic elements of excitatory neurons
        self.growth_curve_dendritic = {
            'growth_curve': "gaussian",
            'growth_rate': 0.0001,  # (elements/ms)
            'continuous': False,
            'eta': 0.1,
            'eps': self.growth_curve_axonal['eps'],
        }

        self.synaptic_elements_E = {
            'Den_ex': self.growth_curve_dendritic,
            'Den_in': self.growth_curve_dendritic,
            'Axon_ex': self.growth_curve_axonal
        }

        self.synaptic_elements_I = {
            'Den_ex': self.growth_curve_dendritic,
            'Den_in': self.growth_curve_dendritic,
            'Axon_in': self.growth_curve_axonal
        }

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

        # external current
        self.poissonExtDict = {'rate': 10., 'origin': 0., 'start': 0.}

    def __create_neurons(self):
        """Create our neurons."""
        self.neuronsE = nest.Create('tif_neuronE', self.populations['E'], {
            'synaptic_elements': self.synaptic_elements_E})
        self.neuronsI = nest.Create('tif_neuronI', self.populations['I'], {
            'synaptic_elements': self.synaptic_elements_I})
        self.poissonExtE = nest.Create('poisson_generator',
                                       self.populations['Poisson'],
                                       params=self.poissonExtDict)
        self.poissonExtI = nest.Create('poisson_generator',
                                       self.populations['Poisson'],
                                       params=self.poissonExtDict)

    def __create_sparse_list(self, length, static_w, sparsity):
        """Create one list to use with SetStatus."""
        weights = []
        valid_values = int(length * sparsity)
        weights = (
            ([float(static_w), ] * valid_values) +
            ([0., ] * int(length - valid_values)))

        random.shuffle(weights)
        return weights

    def __fill_matrix(self, weightlist, static_w, sparsity):
        """Create a weight matrix to use in syn dict."""
        weights = []
        for row in weightlist:
            if isinstance(row, (list, tuple)):
                rowlen = len(row)
                valid_values = int(rowlen * sparsity)
                arow = (
                    ([float(static_w), ] * valid_values) +
                    ([0., ] * int(rowlen - valid_values))
                )
                random.shuffle(arow)
                weights.append(arow)
        return weights

    def __setup_matrix(self, pre_dim, post_dim, static_w, sparsity):
        """Create a weight matrix to use in syn dict."""
        weights = []
        valid_values = int(post_dim * sparsity)
        for i in range(0, pre_dim):
            arow = (
                ([float(static_w), ] * valid_values) +
                ([0., ] * int(post_dim - valid_values))
            )
            random.shuffle(arow)
            weights.append(arow)

        return weights

    def __setup_connections(self):
        """Setup connections."""
        # Global sparsity
        self.sparsity = 0.02
        self.sparsityStim = 0.05

        # Other connection numbers
        self.connectionNumberStim = int((self.populations['STIM'] *
                                         self.populations['R'])
                                        * self.sparsityStim)
        # From the butz paper
        self.connectionNumberExtE = 1
        self.connectionNumberExtI = 1

        # connection dictionaries
        self.connDictExtE = {'rule': 'fixed_indegree',
                             'indegree': self.connectionNumberExtE}
        self.connDictExtI = {'rule': 'fixed_indegree',
                             'indegree': self.connectionNumberExtI}
        self.connDictStim = {'rule': 'fixed_total_number',
                             'N': self.connectionNumberStim}

        # Documentation says things are normalised in the iaf neuron so that
        # weight of 1 translates to 1nS
        # Leave them at 0 to begin with and let Nest for the connections
        # Then, I'll get these and set them individually later
        # I've got to do this because while using MPI etc, each thread has
        # different numbers of connections and I cannot ascertain these numbers
        # before hand.
        self.synDictEE = {'model': 'static_synapse',
                          'weight': 0.,
                          'pre_synaptic_element': 'Axon_ex',
                          'post_synaptic_element': 'Den_ex'}
        self.synDictEI = {'model': 'static_synapse',
                          'weight': 0.,
                          'pre_synaptic_element': 'Axon_ex',
                          'post_synaptic_element': 'Den_ex'}

        self.synDictII = {'model': 'static_synapse',
                          'weight': 0.,
                          'pre_synaptic_element': 'Axon_in',
                          'post_synaptic_element': 'Den_in'}

        self.synDictIE = {'model': 'vogels_sprekeler_synapse',
                          'weight': -0.0000001, 'Wmax': -30000.,
                          'alpha': .32, 'eta': 0.001,
                          'tau': 20., 'pre_synaptic_element': 'Axon_in',
                          'post_synaptic_element': 'Den_in'}

    def __connect_neurons(self):
        """Connect the neuron sets up."""
        nest.Connect(self.poissonExtE, self.neuronsE,
                     conn_spec=self.connDictExtE,
                     syn_spec={'model': 'static_synapse',
                               'weight': self.weightExtE})
        nest.Connect(self.poissonExtI, self.neuronsI,
                     conn_spec=self.connDictExtI,
                     syn_spec={'model': 'static_synapse',
                               'weight': self.weightExtI})

        # all to all
        nest.Connect(self.neuronsE, self.neuronsE,
                     syn_spec=self.synDictEE)
        conns = nest.GetConnections(source=self.neuronsE, target=self.neuronsE)
        weights = self.__create_sparse_list(
            len(conns), self.weightEE, self.sparsity)
        i = 0
        for conn in conns:
            nest.SetStatus([conn], {'weight': weights[i]})
            i = i+1
        print("EE weights set up.")

        nest.Connect(self.neuronsE, self.neuronsI,
                     syn_spec=self.synDictEI)
        conns = nest.GetConnections(source=self.neuronsE, target=self.neuronsI)
        weights = self.__create_sparse_list(
            len(conns), self.weightEI, self.sparsity)
        i = 0
        for conn in conns:
            nest.SetStatus([conn], {'weight': weights[i]})
            i = i+1
        print("EI weights set up.")

        nest.Connect(self.neuronsI, self.neuronsI,
                     syn_spec=self.synDictII)
        conns = nest.GetConnections(source=self.neuronsI, target=self.neuronsI)
        weights = self.__create_sparse_list(
            len(conns), self.weightII, self.sparsity)
        i = 0
        for conn in conns:
            nest.SetStatus([conn], {'weight': weights[i]})
            i = i+1
        print("II weights set up.")

        nest.Connect(self.neuronsI, self.neuronsE,
                     syn_spec=self.synDictIE)
        # conns = nest.GetConnections(source=self.neuronsI,
        #     target=self.neuronsE)
        # Use this to set eta of 98% synapses to 0 so that they're static
        # etas = self.__create_sparse_list(
        #     len(conns), 0.001, self.sparsity)
        # i = 0
        # for conn in conns:
        #     nest.SetStatus([conn], {'eta': etas[i]})
        #     i = i+1
        # print("IE weights set up.")

    def __setup_detectors(self):
        """Setup spike detectors."""
        self.spike_detector_paramsE = {
            'to_file': True,
            'label': 'spikes-' + str(self.rank) + '-E'
        }
        self.spike_detector_paramsI = {
            'to_file': True,
            'label': 'spikes-' + str(self.rank) + '-I'
        }
        self.spike_detector_paramsD = {
            'to_file': True,
            'label': 'spikes-' + str(self.rank) + '-deaffed'
        }

        self.sdE = nest.Create('spike_detector',
                               params=self.spike_detector_paramsE)
        self.sdI = nest.Create('spike_detector',
                               params=self.spike_detector_paramsI)

        nest.Connect(self.neuronsE, self.sdE)
        nest.Connect(self.neuronsI, self.sdI)

    def __setup_files(self):
        """Set up the filenames and handles."""
        # Get the number of spikes in these files and then post-process them to
        # get the firing rate and so on

        self.mean_synaptic_weights_file_name = (
            "00-synaptic-weights-" + str(self.rank) + ".txt")

        self.mean_synaptic_weights_file = open(
            self.mean_synaptic_weights_file_name, 'w')

        self.ca_filename = ("calcium-" +
                            str(self.rank) + ".txt")
        self.ca_file_handle = open(self.ca_filename, 'w')

        self.syn_elms_filename = ("00-synaptic-elements-" +
                                  str(self.rank) + ".txt")
        self.syn_elms_file_handle = open(self.syn_elms_filename, 'w')
        print(
            "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}".format
            (
                "a_ex_total", "a_ex_connected",
                "d_ex_ex_total", "d_ex_ex_connected",
                "d_ex_in_total", "d_ex_in_connected",
                "a_in_total", "a_in_connected",
                "d_in_ex_total", "d_in_ex_connected",
                "d_in_in_total", "d_in_in_connected"
            ),
            file=self.syn_elms_file_handle)

    def setup_simulation(self):
        """Set up simulation."""
        # Nest stuff
        nest.ResetKernel()
        # http://www.nest-simulator.org/sli/setverbosity/
        nest.set_verbosity('M_INFO')
        # unless using the cluster, just use 24 local threads
        # still gives out different spike files because they're different
        # virtual processes
        # Using 1 thread per core, and 24 MPI processes because I want 24
        # different firing rate files - if I don't use MPI, I only get one
        # firing rate file and I'm not sure how the 24 processes each will
        # write to it
        nest.SetKernelStatus(
            {
                'resolution': self.dt,
                'local_num_threads': 1
            }
        )
        # Update the SP interval
        nest.EnableStructuralPlasticity()
        nest.SetStructuralPlasticityStatus({
            'structural_plasticity_update_interval': self.sp_update_interval,
        })

        self.__setup_neurons()
        self.__create_neurons()
        self.__setup_detectors()

        self.__setup_connections()
        self.__connect_neurons()

        self.__setup_files()

        current_simtime = (
            str(nest.GetKernelStatus()['time'] * 1000) + "msec")

        self.dump_ca_concentration()
        self.dump_synaptic_elements()
        self.dump_mean_synaptic_weights()
        self.dump_all_IE_weights("initial_setup-")
        self.dump_all_EE_weights("initial_setup-")

    def stabilise(self, step=False, annotation=""):
        """Stabilise network."""
        sim_steps = numpy.arange(0, self.stabilisation_time,
                                 self.sp_recording_interval)
        for i, j in enumerate(sim_steps):
            self.run_simulation(self.sp_recording_interval, step, annotation)

    def run_simulation(self, simtime=2000, step=False, annotation=""):
        """Run the simulation."""
        sim_steps = numpy.arange(0, simtime)
        if step:
            print("Stepping through the simulation one second at a time")
            for i, step in enumerate(sim_steps):

                nest.Simulate(1000)
                self.dump_mean_synaptic_weights()
        else:
            print("Not stepping through it one second at a time")
            nest.Simulate(simtime*1000)
            current_simtime = (
                str(nest.GetKernelStatus()['time'] * 1000) + "msec")
            self.dump_ca_concentration()
            self.dump_synaptic_elements()
            self.dump_mean_synaptic_weights()
            self.dump_all_IE_weights(annotation)
            self.dump_all_EE_weights(annotation)

            print("Simulation time: " "{}".format(current_simtime))

    def store_pattern(self):
        """ Store a pattern and set up spike detectors."""
        spike_detector_paramsP = {
            'to_file': True,
            'label': ('spikes-' + str(self.rank) + '-pattern-' +
                      str(self.pattern_count))
        }
        spike_detector_paramsB = {
            'to_file': True,
            'label': ('spikes-' + str(self.rank) + '-background-' +
                      str(self.pattern_count))
        }

        local_neurons = nest.GetNodes(
            nest.CurrentSubnet(), {'model': 'tif_neuronE'},
            local_only=False)[0]

        pattern_neurons = random.sample(
            local_neurons,
            self.populations['P'])
        print("ANKUR>> Number of pattern neurons: "
              "{}".format(len(pattern_neurons)))

        # strengthen connections
        connections = nest.GetConnections(source=pattern_neurons,
                                          target=pattern_neurons)
        print("ANKUR>> Number of connections strengthened: "
              "{}".format(len(connections)))
        nest.SetStatus(connections, {"weight": 24.})

        # store these neurons
        self.patterns.append(pattern_neurons)
        # print to file
        file_name = "patternneurons-{}-rank-{}.txt".format(self.pattern_count,
                                                           self.rank)
        file_handle = open(file_name, 'w')
        for neuron in pattern_neurons:
            print(neuron, file=file_handle)
        file_handle.close()

        # background neurons
        background_neurons = list(set(local_neurons) - set(pattern_neurons))
        file_name = "backgroundneurons-{}-rank-{}.txt".format(
            self.pattern_count, self.rank)

        file_handle = open(file_name, 'w')
        for neuron in background_neurons:
            print(neuron, file=file_handle)
        file_handle.close()

        # set up spike detectors
        # pattern
        pattern_spike_detector = nest.Create(
            'spike_detector', params=spike_detector_paramsP)
        nest.Connect(pattern_neurons, pattern_spike_detector)
        # save the detector
        self.sdP.append(pattern_spike_detector)

        # background
        background_spike_detector = nest.Create(
            'spike_detector', params=spike_detector_paramsB)
        nest.Connect(background_neurons, background_spike_detector)
        # save the detector
        self.sdB.append(background_spike_detector)

        # Increment count after it's all been set up
        self.pattern_count += 1
        print("Number of patterns stored: {}".format(self.pattern_count))

    def setup_pattern_for_recall(self, pattern_number):
        """
        Set up a pattern for recall.

        Creates a new poisson generator and connects it to a recall subset of
        this pattern - the poisson stimulus will run for the set recall_time
        from the invocation of this method.
        """
        # set up external stimulus
        stim_time = nest.GetKernelStatus()['time']
        neuronDictStim = {'rate': 200.,
                          'origin': stim_time,
                          'start': 0., 'stop': self.recall_time}
        spike_detector_paramsStim = {
            'to_file': True,
            'label': ('spikes-' + str(self.rank) + '-Stim-' +
                      str(pattern_number))

        }

        stim = nest.Create('poisson_generator', 1,
                           neuronDictStim)
        stim_neurons = nest.Create('parrot_neuron',
                                   self.populations['STIM'])
        nest.Connect(stim, stim_neurons)
        sd = nest.Create('spike_detector',
                         params=spike_detector_paramsStim)
        nest.Connect(stim_neurons, sd)
        self.sdStim.append(sd)
        self.neuronsStim.append(stim_neurons)

        pattern_neurons = self.patterns[pattern_number - 1]
        recall_neurons = random.sample(
            pattern_neurons,
            self.populations['R'])
        print("ANKUR>> Number of recall neurons: "
              "{}".format(len(recall_neurons)))

        nest.Connect(stim_neurons, recall_neurons,
                     conn_spec=self.connDictStim)

        self.recalls.append(recall_neurons)

        # print to file
        file_name = "recallneurons-{}-rank-{}.txt".format(self.pattern_count,
                                                          self.rank)
        file_handle = open(file_name, 'w')
        for neuron in recall_neurons:
            print(neuron, file=file_handle)
        file_handle.close()

        spike_detector_paramsR = {
            'to_file': True,
            'label': ('spikes-' + str(self.rank) + '-recall-' +
                      str(self.pattern_count))
        }
        recall_spike_detector = nest.Create(
            'spike_detector', params=spike_detector_paramsR)
        nest.Connect(recall_neurons, recall_spike_detector)
        # save the detector
        self.sdR.append(recall_spike_detector)
        # nest.SetStatus(recall_neurons, {'I_e': self.recall_ext_i})

    def recall_last_pattern(self, time, step):
        """
        Only setup the last pattern.

        An extra helper method, since we'll be doing this most.
        """
        self.recall_pattern(time, step, self.pattern_count)

    def recall_pattern(self, time, step, pattern_number):
        """Recall a pattern."""
        self.setup_pattern_for_recall(pattern_number)
        self.run_simulation(time, step)

    def deaff_last_pattern(self):
        """
        Deaff last pattern.

        An extra helper method, since we'll be doing this most.
        """
        self.deaff_pattern(self.pattern_count - 1)

    def deaff_pattern(self, pattern_number):
        """Deaff the network."""
        pattern_neurons = self.patterns[pattern_number - 1]
        deaffed_neurons = random.sample(
            pattern_neurons,
            self.populations['D'])
        print("ANKUR>> Number of deaff neurons: "
              "{}".format(len(deaffed_neurons)))
        nest.SetStatus(deaffed_neurons, {'I_e': 0.})

        deaff_spike_detector = nest.Create(
            'spike_detector', params=self.spike_detector_paramsD)
        nest.Connect(deaffed_neurons, deaff_spike_detector)
        # save the detector
        self.sdL.append(deaff_spike_detector)

    def dump_all_IE_weights(self, annotation):
        """Dump all IE weights to a file."""
        file_name = ("synaptic-weight-IE-" + annotation +
                     "-{}-{}".format(
                         self.rank,
                         nest.GetKernelStatus()['time']) +
                     ".txt")
        file_handle = open(file_name, 'w')
        connections = nest.GetConnections(source=self.neuronsI,
                                          target=self.neuronsE)
        weights = nest.GetStatus(connections, "weight")
        print(weights, file=file_handle)
        file_handle.close()

    def dump_all_EE_weights(self, annotation):
        """Dump all EE weights to a file."""
        file_name = ("synaptic-weight-EE-" + annotation +
                     "-{}-{}".format(
                         self.rank,
                         nest.GetKernelStatus()['time']) +
                     ".txt")
        file_handle = open(file_name, 'w')
        connections = nest.GetConnections(source=self.neuronsE,
                                          target=self.neuronsE)
        weights = nest.GetStatus(connections, "weight")
        print(weights, file=file_handle)
        file_handle.close()

    def dump_ca_concentration(self):
        """Dump calcium concentration."""
        loc_e = [stat['global_id'] for stat in nest.GetStatus(self.neuronsE)
                 if stat['local']]
        loc_i = [stat['global_id'] for stat in nest.GetStatus(self.neuronsI)
                 if stat['local']]
        ca_e = numpy.mean(nest.GetStatus(loc_e, 'Ca'))
        ca_i = numpy.mean(nest.GetStatus(loc_i, 'Ca'))
        print("{}\t{}".format(ca_e, ca_i), file=self.ca_file_handle)

    def dump_synaptic_elements(self):
        """Dump number of synaptic elements."""
        loc_e = [stat['global_id'] for stat in nest.GetStatus(self.neuronsE)
                 if stat['local']]
        loc_i = [stat['global_id'] for stat in nest.GetStatus(self.neuronsI)
                 if stat['local']]
        syn_elems_e = nest.GetStatus(loc_e, 'synaptic_elements')
        syn_elems_i = nest.GetStatus(loc_i, 'synaptic_elements')

        # Only need presynaptic elements to find number of synapses
        # Excitatory neuron set
        axons_ex_total = sum(neuron['Axon_ex']['z'] for neuron in
                             syn_elems_e)
        axons_ex_connected = sum(neuron['Axon_ex']['z_connected'] for neuron in
                                 syn_elems_e)
        dendrites_ex_ex_total = sum(neuron['Den_ex']['z'] for neuron in
                                    syn_elems_e)
        dendrites_ex_ex_connected = sum(neuron['Den_ex']['z_connected'] for
                                        neuron in syn_elems_e)
        dendrites_ex_in_total = sum(neuron['Den_in']['z'] for neuron in
                                    syn_elems_e)
        dendrites_ex_in_connected = sum(neuron['Den_in']['z_connected'] for
                                        neuron in syn_elems_e)

        # Inhibitory neuron set
        axons_in_total = sum(neuron['Axon_in']['z'] for neuron in
                             syn_elems_i)
        axons_in_connected = sum(neuron['Axon_in']['z_connected'] for neuron in
                                 syn_elems_i)
        dendrites_in_ex_total = sum(neuron['Den_ex']['z'] for neuron in
                                    syn_elems_i)
        dendrites_in_ex_connected = sum(neuron['Den_ex']['z_connected'] for
                                        neuron in syn_elems_i)
        dendrites_in_in_total = sum(neuron['Den_in']['z'] for neuron in
                                    syn_elems_i)
        dendrites_in_in_connected = sum(neuron['Den_in']['z_connected'] for
                                        neuron in syn_elems_i)

        print(
            "{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}".format
            (
                axons_ex_total, axons_ex_connected,
                dendrites_ex_ex_total, dendrites_ex_ex_connected,
                dendrites_ex_in_total, dendrites_ex_in_connected,
                axons_in_total, axons_in_connected,
                dendrites_in_ex_total, dendrites_in_ex_connected,
                dendrites_in_in_total, dendrites_in_in_connected,
            ),
            file=self.syn_elms_file_handle)

    def dump_mean_synaptic_weights(self):
        """Dump synaptic weights."""
        conns = nest.GetConnections(target=self.neuronsE,
                                    source=self.neuronsI)
        weightsIE = nest.GetStatus(conns, "weight")
        mean_weightsIE = numpy.mean(weightsIE)

        conns = nest.GetConnections(target=self.neuronsI,
                                    source=self.neuronsI)
        weightsII = nest.GetStatus(conns, "weight")
        mean_weightsII = numpy.mean(weightsII)

        conns = nest.GetConnections(target=self.neuronsI,
                                    source=self.neuronsE)
        weightsEI = nest.GetStatus(conns, "weight")
        mean_weightsEI = numpy.mean(weightsEI)

        conns = nest.GetConnections(target=self.neuronsE,
                                    source=self.neuronsE)
        weightsEE = nest.GetStatus(conns, "weight")
        mean_weightsEE = numpy.mean(weightsEE)

        statement_w = "{0}\t{1}\t{2}\t{3}\n".format(mean_weightsEE,
                                                    mean_weightsEI,
                                                    mean_weightsII,
                                                    mean_weightsIE)

        self.mean_synaptic_weights_file.write(statement_w)
        self.mean_synaptic_weights_file.flush()

if __name__ == "__main__":
    step = False
    simulation = Sinha2016()
    simulation.setup_simulation()

    simulation.stabilise(step, "initial_stabilisation")

    # store and stabilise patterns
    for i in range(0, simulation.numpats):
        simulation.store_pattern()
        simulation.stabilise(step, "pattern_stabilisation" + str(i))

    # Only recall the last pattern because nest doesn't do snapshots
    # simulation.deaff_last_pattern()
    # simulation.stabilise(step, "deaffed_last_pattern")
    # simulation.recall_last_pattern(50, step)
