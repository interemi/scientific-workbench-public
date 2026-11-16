# Catalog crossmatch I/O at 50,000 rows per input

The Core and optional STILTS catalog routes in `b88f0e8` were run on
the same Apple M1 Pro with 16 GiB of RAM and macOS 27.0.1. The inputs
were two 1,430,661-byte synthetic CSVs. Each contained 50,000 sources
on a sky grid. Right-catalog positions differed by 0.36 arcseconds
in declination for 45,000 sources and by 36 arcseconds for the other
5,000. With the one-arcsecond match radius, the expected pairs are
known by construction.

The three paired trials alternated execution order. Core returned
ECSV using the project's Python 3.11 Core environment. The bundled
STILTS wrapper returned CSV using the installed STILTS 3.5-6 under
Java 21. Each run used a new output directory. Core counters were
read immediately before exit. STILTS counters sampled the Java
child every 10 ms and report the maximum observed value, which
can miss I/O near process exit.

| Paired measurement | Core Python process | STILTS Java child |
| --- | ---: | ---: |
| Median route elapsed time | 0.841 s | 0.825 s |
| Maximum attributed disk read | 12 KiB | 24 KiB |
| Maximum attributed disk write | 2.61 MiB | 2.62 MiB |
| Maximum observed physical memory footprint | 112.1 MiB | 224.5 MiB |
| Output table size | 2,722,382 bytes | 2,713,936 bytes |
| Expected pairs and separations verified | 3/3 | 3/3 |
| Complete input and output hash records | 3/3 | 0/3 |

The paired read observations used warm filesystem caches. An earlier
Core run attributed 8.91 MiB of reads with the same inputs. The
reference write threshold for this fixture is 4 MiB per measured
process, which allows for allocation differences. For Core, the
development Mac has a 16 MiB reference read threshold for this
fixture. A cold-read STILTS threshold needs a cold-cache series.
The counters cover the measured processes. The STILTS Python wrapper
and system services can add I/O beyond the Java counters.

## Evidence integrity

Both routes returned exactly the 45,000 expected ID pairs. Every
separation agreed with 0.36 arcseconds within `1e-6` arcseconds.
Both input hashes and the output table hash matched the manifest
in every run. The synthetic input files retained their hashes.

STILTS reported a successful tool outcome in each trial. Its
manifest marked `summary.json` absent and omitted its hash while the
summary existed after completion. The wrapper calls `write_manifest`
from the command handler before `main` emits the summary. This is
an artifact evidence failure, tracked under P2.08. The STILTS
measurements establish performance and pair agreement for this
fixture. Complete hash verification is pending a fix and a fresh run.
