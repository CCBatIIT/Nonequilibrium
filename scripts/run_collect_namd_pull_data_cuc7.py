"""
write nc file which contains
'zF_t', 'wF_t', 'zR_t', 'wR_t', 'ks',
'lambda_F', 'lambda_R', 'pulling_times', 'dt'
"""
from __future__ import print_function
from __future__ import division

import os
import argparse

import numpy as np
import netCDF4 as nc

from models_1d import V
from _IO import save_to_nc

parser = argparse.ArgumentParser()

parser.add_argument("--forward_pull_dir", type=str, default="forward")
parser.add_argument("--backward_pull_dir", type=str, default="backward")

parser.add_argument("--forward_force_file", type=str, default="cuc7.force")
parser.add_argument("--backward_force_file", type=str, default="cuc7.force")

# will load load all files from range[0] to file_range[1]-1
parser.add_argument("--range", type=str,  default="0 10")

# which trajectory file to exclude
parser.add_argument("--exclude", type=str,  default=" ")

parser.add_argument("--pulling_speed", type=float,  default=0.1)  # Angstrom per ps = speed in A per step / (2*10**(-3))
parser.add_argument("--force_constant", type=float,  default=7.2) # kcal/mol/A^2
parser.add_argument("--lambda_range", type=str,  default="-20. 20.") # Angstrom

parser.add_argument("--out", type=str,  default="pull_data.nc")

args = parser.parse_args()

KB = 0.0019872041   # kcal/mol/K
TEMPERATURE = 300.
BETA = 1/KB/TEMPERATURE


def _lambda_t(pulling_times, pulling_speed, lambda_0):
    """
    :param pulling_times: ndarray of float, ps
    :param pulling_speed: float, Angstrom per ps
    :param lambda_0: float, Angstrom
    :return: lambda_t, ndarray of float
    """
    lambda_t = pulling_times*pulling_speed + lambda_0
    return lambda_t


def _work_integrate(lambda_t, z_t, k):
    """
    lambda_t    :   np.array of shape (times), restrained center
    z_t         :   np.array of shape (times), restrained coordinate
    k           :   float, harmonic force constant
    """
    assert lambda_t.ndim == z_t.ndim == 1, "lambda_t and z_t must be 1d"
    assert lambda_t.shape == z_t.shape, "lambda_t and z_t must have the same shape"

    times = lambda_t.shape[0]
    w_t = np.zeros(times, dtype=float)

    # eq (3.4) in Christopher Jarzynski, Prog. Theor. Phys. Suppl 2006, 165, 1
    #w_t[1:] = - 2 * k * np.cumsum( (z_t[:-1] - lambda_t[:-1]) * (lambda_t[1:] - lambda_t[:-1]) )

    # in D. Minh and J. Chodera J Chem Phys 2009, 131, 134110. in Potential of mean force section
    # this is consistent with 1d model
    w_t[1:] = V(z_t[1:], k, lambda_t[1:]) - V(z_t[1:], k, lambda_t[:-1])
    w_t = np.cumsum(w_t)

    return w_t


def _time_z_work(tcl_force_out_file, pulling_speed, lambda_0, k):
    """
    :param tcl_force_out_file: str, file name
    :param pulling_speed: float, Angstrom per ps
    :param lambda_0: float, initial value of lambda
    :return: (pulling_times, z_t, w_t) in (ps, Angstrom, kcal/mol)
    """
    data = np.loadtxt(tcl_force_out_file)

    pulling_times = data[:, 0]
    z_t = data[:, 1]
    #forces = data[:, 2]

    #nsteps = len(pulling_times)

    #w_t = np.zeros([nsteps], dtype=float)
    #dts = pulling_times[1:] - pulling_times[:-1]

    #w_t[1:] = pulling_speed * forces[:-1] * dts
    #w_t = np.cumsum(w_t)

    lambda_t = _lambda_t(pulling_times, pulling_speed, lambda_0)
    w_t = _work_integrate(lambda_t, z_t, k)

    return pulling_times, z_t, w_t

# -----------


ks = 100. * BETA * args.force_constant             # kT per nm^2
lambda_min = float(args.lambda_range.split()[0])
lambda_max = float(args.lambda_range.split()[1])

start = int(args.range.split()[0])
end = int(args.range.split()[1])

exclude = [int(s) for s in args.exclude.split()]
print("exclude", exclude)

indices_to_collect = [i for i in range(start, end) if i not in exclude]

forward_files = [os.path.join(args.forward_pull_dir, "%d"%i, args.forward_force_file)
                  for i in indices_to_collect]
backward_files = [os.path.join(args.backward_pull_dir, "%d"%i, args.backward_force_file)
                  for i in indices_to_collect]

for f in forward_files:
    assert os.path.exists(f), f + " does not exit."
for f in backward_files:
    assert os.path.exists(f), f + " does not exit."

pulling_times_F, _, _ = _time_z_work(forward_files[0], args.pulling_speed, lambda_min, args.force_constant)
lambda_F = _lambda_t(pulling_times_F, args.pulling_speed, lambda_min)

pulling_times_R, _, _ = _time_z_work(backward_files[0], -args.pulling_speed, lambda_max, args.force_constant)
lambda_R = _lambda_t(pulling_times_R, -args.pulling_speed, lambda_max)

dt = pulling_times_F[1] - pulling_times_F[0]
nsteps = pulling_times_F.shape[0]
assert nsteps == pulling_times_R.shape[0]

total_ntrajs = len(forward_files)
zF_ts = np.zeros([total_ntrajs, nsteps], dtype=float)
wF_ts = np.zeros([total_ntrajs, nsteps], dtype=float)

zR_ts = np.zeros([total_ntrajs, nsteps], dtype=float)
wR_ts = np.zeros([total_ntrajs, nsteps], dtype=float)


for i, (f_file, b_file) in enumerate(zip(forward_files, backward_files)):
    print("loading " + f_file)
    _, zF_t, wF_t = _time_z_work(f_file, args.pulling_speed, lambda_min, args.force_constant)
    assert zF_t.shape[0] == nsteps, f_file + " do not have correct timesteps"
    zF_ts[i, :] = zF_t
    wF_ts[i, :] = wF_t

    print("loading " + b_file)
    _, zR_t, wR_t = _time_z_work(b_file, -args.pulling_speed, lambda_max, args.force_constant)
    assert zR_t.shape[0] == nsteps, b_file + " do not have correct timesteps"
    zR_ts[i, :] = zR_t
    wR_ts[i, :] = wR_t

lambda_F /= 10.     # to nm
lambda_R /= 10.     # to nm
zF_ts /= 10.        # to nm
wF_ts *= BETA       # kcal/mol to KT/mol

zR_ts /= 10.        # to nm
wR_ts *= BETA       # kcal/mol to KT/mol

out_nc_handle = nc.Dataset(args.out, "w", format="NETCDF4")

data = {"dt" : np.array([dt], dtype=float),
        "pulling_times" : pulling_times_F,
        "ks" : np.array([ks]),
        "lambda_F" : lambda_F,
        "wF_t" : wF_ts,
        "zF_t" : zF_ts,

        "lambda_R": lambda_R,
        "wR_t" : wR_ts,
        "zR_t" : zR_ts,
        }

save_to_nc(data, out_nc_handle)
out_nc_handle.close()

print("DONE")
