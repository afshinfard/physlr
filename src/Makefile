CXXFLAGS=-g -O3 -Wall -Werror -Wno-error=unknown-pragmas -std=c++11 -pthread -I./include -I./vendor -fopenmp
LDLIBS=-lz

#all: physlr-filter-barcodes physlr-indexlr physlr-overlap  
#all: physlr-filter-barcodes-new
#all: parallel
#all: filter-minimizers physlr-filter-barcodes-new-copy-copy
all: physlr-filter-barcodes-new
#all: physlr-filter-barcodes-new-plot

clean:
	#rm -f physlr-filter-barcodes physlr-indexlr physlr-overlap
	rm -f parallel

# Check the C++ source code for errors with clang-tidy.
lint:
	clang-tidy -warnings-as-errors='*' include/*.h *.cc -- -std=c++11 -x c++ -I./include -I./vendor

check: check-physlr-index-fasta check-physlr-index-fastq check-physlr-filter-barcodes

check-physlr-index-fasta: all
	./physlr-indexlr -t16 -k100 -w5 data/mt.fa | diff -q - data/mt.physlr.tsv.good

check-physlr-index-fastq: all
	./physlr-indexlr -t16 -k100 -w5 data/tiny.fq | diff -q - data/tiny.physlr.tsv.good

check-physlr-filter-barcodes: all
	./physlr-filter-barcodes data/f1chr4-head50.tsv -o data/f1chr4-head50.n100-1000.tsv -n100 -N1000
	./data/checkMx.sh data/f1chr4-head50.n100-1000.good.tsv data/f1chr4-head50.n100-1000.tsv

check-physlr-filter-bxmx: all
	env PYTHONPATH=.. /projects/btl/aafshinfard/virtuEnv/pypy3/bin/pypy3 ../bin/physlr filter-barcodes -n100 -N1000 data/f1chr4-head50.tsv > python-fb.tsv
	env PYTHONPATH=.. /projects/btl/aafshinfard/virtuEnv/pypy3/bin/pypy3 ../bin/physlr filter-minimizers -V2 -C 5 python-fb.tsv > python-fm.tsv
	./physlr-filter-barcodes-new data/f1chr4-head50.tsv -o cpp-ff.tsv -n100 -N1000 -C5
	./data/checkMx.sh python-fm.tsv cpp-ff.tsv 
