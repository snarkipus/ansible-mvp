#!/usr/bin/env perl
use strict;
use warnings;
use File::Basename qw(dirname);
use File::Temp qw(tempfile);

# Minimal required extractor for later provenance stages.
# Usage: extract_required.pl <sim-out.dat> <required.csv>

my ($input_path, $output_path) = @ARGV;
if (!defined $input_path || !defined $output_path) {
    die "Usage: extract_required.pl <sim-out.dat> <required.csv>\n";
}

open my $in, '<', $input_path or die "Cannot read $input_path: $!\n";

my $header = <$in>;
defined $header or die "Input is empty: $input_path\n";
chomp $header;
die "Unexpected header in $input_path\n"
    unless $header eq 'logical_group,example,bytes,sha256_prefix';

my ($out, $temporary_path) = tempfile(
    '.required.csv.XXXXXX',
    DIR => dirname($output_path),
    UNLINK => 1,
);
print {$out} "logical_group,example,bytes,sha256_prefix\n";
while (my $line = <$in>) {
    chomp $line;
    next if $line eq '';
    my ($logical_group, $example, $bytes, $sha_prefix) = split /,/, $line;
    next unless defined $logical_group && $logical_group eq 'dirC';
    print {$out} join(',', $logical_group, $example, $bytes, $sha_prefix), "\n";
}

close $out or die "Cannot close temporary output $temporary_path: $!\n";
close $in or die "Cannot close $input_path: $!\n";
rename $temporary_path, $output_path
    or die "Cannot publish $output_path from $temporary_path: $!\n";
