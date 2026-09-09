"""eBook Metamend: repair ebook metadata without letting a source lie to you.

The filenames are the ground truth. Online sources are witnesses, scored against
the filename and its author, and only trusted when the evidence clears a
threshold. See :mod:`ebook_metamend.matching` for the safety model.
"""

__version__ = '1.0.0'

__all__ = ['__version__']
