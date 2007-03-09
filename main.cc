#include <iostream>
#include <fstream>
#include <unistd.h>

const char* df1str = "data file test: ";
const char* df2str = "another data file: ";
const char ds2offset = 3;
const char ds3offset = 3;
const char ds4offset = 3;

int main(int argc, const char* argv[])
{
  if (argc < 2) return -1;

  std::cout << "Consistency Test Script Test App" << std::endl;
  sleep(2);
  std::cout << "Doing output..." << std::endl;
  
  std::ofstream fp;

  switch (argv[1][0]) {
  case 'a':
    fp.open("outfile.dat");
    fp << df1str << argv[1][0] << std::endl;
    fp.close();
    break;
  case 'b':
    fp.open("outfile.dat");
    fp << "# this is a comment" << std::endl;
    fp << df1str << argv[1][0] << std::endl;
    fp.close();
    break;
  case 'c':
    fp.open("outfile.dat");
    fp << df1str << argv[1][0] << std::endl;
    fp.close();
    break;
  case 'd':
    fp.open("outfile.dat");
    fp << df1str << (argv[1][0] - ds2offset) << std::endl;
    fp.close();
  case 'e':
    fp.open("outfile.dat", std::ios_base::app);
    fp << df1str << (argv[1][0] - ds3offset) << std::endl;
    fp.close();
  case 'f':
    fp.open("outfile.dat", std::ios_base::app);
    fp << df1str << (argv[1][0] - ds4offset) << std::endl;
    fp.close();
    fp.open("outfile2.dat");
    fp << df2str << argv[1][0] << std::endl;
    fp.close();
    break;
  default:
    return -2;
  }

  return 0;
}
