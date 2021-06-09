#!/usr/bin/env python
# encoding: utf-8

# The MIT License (MIT)

# Copyright (c) 2020 CoML

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# AUTHORS
# Rachid RIAD & Hadrien TITEUX
"""
##########
Alignement and disorder
##########

"""
from abc import ABCMeta, abstractmethod
from collections import Counter
from typing import TYPE_CHECKING, Union
from typing import Tuple, Optional, Iterable, Iterator, List

import numpy as np

from .dissimilarity import AbstractDissimilarity, CombinedCategoricalDissimilarity

from .continuum import Continuum, Annotator, Unit

UnitsTuple = List[Tuple['Annotator', Optional['Unit']]]


class SetPartitionError(Exception):
    """Exception raised for errors in the partition of units of continuum.

    Attributes:
        message -- explanation of the error
    """


class AbstractAlignment(metaclass=ABCMeta):

    @property
    @abstractmethod
    def disorder(self) -> float:
        """Return the disorder for an alignment, if it has already been computed
        beforehand

        >>> aligment.disorder
        ... 0.123

        """

    @abstractmethod
    def compute_disorder(self, dissimilarity: AbstractDissimilarity) -> float:
        """Compute the disorder for that alignment"""


class UnitaryAlignment:
    """Unitary Alignment

    Parameters
    ----------
    n_tuple :
        n-tuple where n is the number of annotators of the continuum
        This is a list of (annotator, segment) couples
    """

    def __init__(self, n_tuple: UnitsTuple):
        assert len(n_tuple) >= 2
        self._n_tuple: UnitsTuple = n_tuple
        self._disorder: Optional[float] = None

    @property
    def n_tuple(self):
        return self._n_tuple

    @n_tuple.setter
    def n_tuple(self, n_tuple: UnitsTuple):
        self._n_tuple = n_tuple
        self._disorder = None

    @property
    def disorder(self) -> float:
        """
        Disorder of the alignment.
        Raises ValueError if self.compute_disorder(dissimilarity) hasn't been called
        before.
        """
        if self._disorder is None:
            raise ValueError("Disorder hasn't been computed. "
                             "Call `compute_disorder()` first to compute it.")
        else:
            return self._disorder

    @property
    def nb_units(self):
        """The number of non-empty units in the unitary alignment."""
        return sum(1 for _ in filter((lambda annot_unit: annot_unit[1] is not None), self._n_tuple))

    @disorder.setter
    def disorder(self, value: float):
        self._disorder = value

    def compute_disorder(self, dissimilarity: AbstractDissimilarity):
        """
        Building a fake one-element alignment to compute the disorder
        """
        fake_alignment = Alignment([self])
        self._disorder = fake_alignment.compute_disorder(dissimilarity)
        return self._disorder


class Alignment(AbstractAlignment):
    """Alignment

    Parameters
    ----------
    unitary_alignments :
        set of unitary alignments that make a partition of the set of
        units/segments
    continuum : optional Continuum
        Continuum where the alignment is from
    check_validity: bool
        Check the validity of that Alignment against the specified continuum
    """

    def __init__(self,
                 unitary_alignments: Iterable[UnitaryAlignment],
                 continuum: Optional['Continuum'] = None,
                 check_validity: bool = False
                 ):
        self.unitary_alignments = list(unitary_alignments)
        self.continuum = continuum
        self._disorder: Optional[float] = None

        if not check_validity:
            return
        else:
            self.check()

    def __getitem__(self, *keys: Union[int, Tuple[int, 'Annotator']]):
        # TODO : test and document
        if len(keys) == 1:
            idx = keys[0]
            return self.unitary_alignments[idx]
        elif len(keys) == 2:
            idx, annotator = keys
            annotator_idx = self.annotators.index(annotator)
            return self.unitary_alignments[idx].n_tuple[annotator_idx]
        else:
            raise KeyError("Invalid number of items in key")

    def __iter__(self) -> Iterator[UnitaryAlignment]:
        return iter(self.unitary_alignments)

    @property
    def annotators(self):
        return [annotator for annotator, _
                in self.unitary_alignments[0].n_tuple]

    @property
    def mean_nb_unit_per_annotator(self):
        if self.continuum is not None:
            return self.continuum.avg_num_annotations_per_annotator
        else:
            return sum(unitary_alignment.nb_units for unitary_alignment in self) / self.num_annotators

    @property
    def num_unitary_alignments(self):
        return len(self.unitary_alignments)

    @property
    def num_annotators(self):
        return len(self.unitary_alignments[0].n_tuple)

    @property
    def disorder(self):
        # TODO : doc
        if self._disorder is None:
            self._disorder = (sum(u_align.disorder for u_align
                                  in self.unitary_alignments)
                              / self.mean_nb_unit_per_annotator)
        return self._disorder

    def compute_disorder(self, dissimilarity: AbstractDissimilarity):
        # TODO : doc
        disorder_args = dissimilarity.build_args(self)
        unit_ids = np.arange(self.num_unitary_alignments, dtype=np.int32)
        unit_ids = np.vstack([unit_ids] * self.num_annotators)
        unit_ids = unit_ids.swapaxes(0, 1)
        disorders = dissimilarity(unit_ids, *disorder_args)
        for i, disorder in enumerate(disorders):
            self.unitary_alignments[i].disorder = disorder
        self._disorder = (dissimilarity(unit_ids, *disorder_args).sum()
                          / self.mean_nb_unit_per_annotator)
        return self._disorder

    def gamma_k_disorder(self, dissimilarity: 'CombinedCategoricalDissimilarity', category: Optional[str]) -> float:
        """
        Returns the gamma-k or gamma-cat metric disorder (detailed in https://hal.archives-ouvertes.fr/hal-01712281)
        Of the alignment.

        Parameters
        ----------
        dissimilarity:
        the dissimilarity measure to be used in the algorithm. Raises ValueError if it is not a combined categorical
        dissimilarity, as gamma-cat requires both positional and categorical dissimilarity.
        category:
        The category to be used as reference for gamma-k. Set it as None for computing the gamma-cat disorder.
        """
        if not isinstance(dissimilarity, CombinedCategoricalDissimilarity):
            raise TypeError("Cannot compute gamma-k or gamma-cat with a best alignment computed with a "
                            "non-combined dissimilarity.")
        if category is not None and category not in self.continuum.categories:
            return 0  # If the category if not in the continuum, we consider that the annotators agree about that.
        total_disorder = 0
        total_weight = 0
        for unitary_alignment in self:
            nv = unitary_alignment.nb_units
            if nv < 2:
                weight_base = 0
            else:
                weight_base = 1 / (nv - 1)
            for i, (_, unit1) in enumerate(unitary_alignment.n_tuple):
                for _, unit2 in unitary_alignment.n_tuple[i+1:]:
                    # Gamma-k
                    if unit1 is None or unit2 is None:
                        continue
                    if category is not None and unit1.annotation != category and unit2.annotation != category:
                        continue
                    weight_confidence = max(0, 1 - (dissimilarity.positional_dissim.dpos(unit1, unit2)))
                    cat_dissim = dissimilarity.categorical_dissim.dcat(unit1, unit2)
                    weight = weight_base * weight_confidence
                    total_disorder += cat_dissim * weight_base
                    total_weight += weight_base
        if total_weight == 0:
            return np.NaN
        return total_disorder / total_weight

    def check(self, continuum: Optional[Continuum] = None):
        """
        Checks that an alignment is a valid partition of a Continuum. That is,
        that all annotations from the referenced continuum *can be found*
        in the alignment and can be found *only once*. Empty units are not
        taken into account.

        Parameters
        ----------
        continuum: optional Continuum
            Continuum to check the alignment against. If none is specified,
            will try to use the one set at instanciation.

        Raises
        -------
        ValueError, SetPartitionError
        """
        if continuum is None:
            if self.continuum is None:
                raise ValueError("No continuum was set")
            continuum = self.continuum

        # simple check: verify that all unitary alignments have the same length
        first_len = len(self.unitary_alignments[0].n_tuple)
        for unit_align in self.unitary_alignments:
            if len(unit_align.n_tuple) != first_len:
                raise ValueError(
                    f"Unitary alignments {self.unitary_alignments[0]} and"
                    f"{unit_align} don't have the same amount of units tuples")

        # set partition tests for the unitary alignments
        continuum_tuples = set()
        for annotator, unit in continuum:
            continuum_tuples.add((annotator, unit))

        alignment_tuples = list()
        for unitary_alignment in self.unitary_alignments:
            for (annotator, unit) in unitary_alignment.n_tuple:
                if unit is None:
                    continue
                alignment_tuples.append((annotator, unit))

        # let's first look for missing ones, then for repeated assignments
        missing_tuples = continuum_tuples - set(alignment_tuples)
        if missing_tuples:
            repeated_tuples_str = ', '.join(f"{annotator}->{unit}"
                                            for annotator, unit in missing_tuples)

            raise SetPartitionError(f'{repeated_tuples_str} '
                                    f'not in the set of unitary alignments')

        tuples_counts = Counter(alignment_tuples)
        repeated_tuples = {tup for tup, count in tuples_counts.items() if count > 1}
        if repeated_tuples:
            repeated_tuples_str = ', '.join(f"{annotator}->{unit}"
                                            for annotator, unit in repeated_tuples)

            raise SetPartitionError(f'{repeated_tuples_str} '
                                    f'are found more than once in the set '
                                    f'of unitary alignments')

    def _repr_png_(self):
        """IPython notebook support

        See also
        --------
        :mod:`pygamma_agreement.notebook`
        """

        from .notebook import repr_alignment
        return repr_alignment(self)
