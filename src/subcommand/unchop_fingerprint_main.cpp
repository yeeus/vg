#include "subcommand.hpp"
#include <vg/io/vpkg.hpp>
#include <handlegraph/path_handle_graph.hpp>
#include "../algorithms/unchop_fingerprint.hpp"
#include <iostream>

using namespace vg::subcommand;

int main_unchop_fingerprint(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: vg unchop-fingerprint graph.vg\n";
        return 1;
    }
    auto graph = vg::io::VPKG::load_one<handlegraph::PathHandleGraph>(argv[2]);
    std::cout << vg::unchop_benchmark::fingerprint(*graph) << "\n";
    return 0;
}
static Subcommand vg_unchop_fingerprint("unchop-fingerprint",
    "strict graph fingerprint for the Cactus unchop benchmark", main_unchop_fingerprint);
