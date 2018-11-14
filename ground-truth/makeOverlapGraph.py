#!/usr/bin/env python3
import networkx as nx
import argparse

'''
Given a molecule BED file generated by bedtools intersect, produce an overlap graph of barcodes (Nodes: barcodes; Edges: molecule overlap based on alignments)
'''

def readBED(BEDfilename, min_overlap, prefix):
	overlap_graph = nx.Graph()

	out_graph = open(prefix + ".overlap_graph_molec.dot", 'w')
	out_graph.write("strict graph  {\n")

	out_tsv = open(prefix + ".overlap_graph_molec.tsv", 'w')
	out_tsv.write("U\tV\tn\n")
	
	#stores molecule nodees
	molec_id = {}
	
	with open(BEDfilename, 'r') as BED:
		for bed_entry in BED:
			bed_entry = bed_entry.strip().split("\t")
			(chr1, start1, end1, bx1, mi1) = (bed_entry[0], int(bed_entry[1]), int(bed_entry[2]), bed_entry[3], int(bed_entry[4]))
			(chr2, start2, end2, bx2, mi2) = (bed_entry[5], int(bed_entry[6]), int(bed_entry[7]), bed_entry[8], int(bed_entry[9]))
			overlap = int(bed_entry[10])
			if overlap < min_overlap:
				continue
			if mi1 == mi2:
				molec_id[bx1 + '_' +  str(mi1)] = end1 - start1
				if overlap_graph.has_node(bx1):
					overlap_graph.node[bx1]['l'] += end1 - start1
				else:
					overlap_graph.add_node(bx1, l = end1 - start1)
			if start1 < start2 or (start1 == start2 and bx1 < bx2):
				#print to molecule graph
				out_graph.write("\t\"%s_%s\" -- \"%s_%s\"\t[n=%d];\n" % (bx1, mi1, bx2, mi2, overlap))
				out_tsv.write("%s_%s\t%s_%s\t%d\n" % (bx1, mi1, bx2, mi2, overlap))
				# record overlap graph edge
				if overlap_graph.has_edge(bx1, bx2):
					# print("WARNING: Already an edge between %s and %s" % (BX, overlap.data))
					overlap_graph[bx1][bx2]['n'] += overlap
				else:
					if not overlap_graph.has_node(bx1):
						overlap_graph.add_node(bx1, l = 0)
					if not overlap_graph.has_node(bx2):
						overlap_graph.add_node(bx2, l = 0)
					overlap_graph.add_edge(bx1, bx2, n=overlap)
	
	out_tsv.write("\nU\tl\n")
	#output remaining molecule graph
	for id in molec_id:
		out_graph.write("\t\"%s\"\t[l=%d];\n" % (id, molec_id[id]))
		out_tsv.write("%s\t%d\n" % (id, molec_id[id]))
						
	out_graph.write("}\n")
	print("DONE building molecule graph")
	print("DONE writing molecule graph")
	out_graph.close()
	out_tsv.close()
	
	print("DONE building barcode graph")
	out_graph = open(prefix + ".overlap_graph.dot", 'w')
	out_tsv = open(prefix + ".overlap_graph.tsv", 'w')
	out_graph.write("strict graph  {\n")
	out_tsv.write("U\tV\tn\n")
	for edge in overlap_graph.edges():
		out_str = "\t\"%s\" -- \"%s\"\t[n=%d];\n" % (edge[0], edge[1], overlap_graph[edge[0]][edge[1]]["n"])
		out_graph.write(out_str)
		out_str = "%s\t%s\t%d\n" % (edge[0], edge[1], overlap_graph[edge[0]][edge[1]]["n"])
		out_tsv.write(out_str)
	out_tsv.write("\nU\tl\n")
	for node in overlap_graph.nodes():
		out_str = "\t\"%s\"\t[l=%d];\n" % (node, overlap_graph.node[node]['l'])
		out_graph.write(out_str)
		out_str = "%s\t%d\n" % (node, overlap_graph.node[node]['l'])
		out_tsv.write(out_str)
	out_graph.write("}\n")
	print("DONE writing barcode graph")
	out_graph.close()
	out_tsv.close()

def main():
	parser = argparse.ArgumentParser(description="Produce a barcode overlap graph based on read alignments")
	parser.add_argument("BED", type=str, help="Overlap BED file")
	parser.add_argument("-m", type=int, help='Minimum overlap between molecules to create edge', default=500, required=False)
	parser.add_argument("-p", type=str, help="Prefix for output files", default="barcode_overlap", required=False)
	args = parser.parse_args()

	readBED(args.BED, args.m, args.p)

if __name__ == "__main__":
	main()