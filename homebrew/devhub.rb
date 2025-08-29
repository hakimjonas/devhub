class Devhub < Formula
  include Language::Python::Virtualenv

  desc "CLI tool to bundle Jira tickets, GitHub PRs, diffs, and comments for code review"
  homepage "https://github.com/hakimjonas/devhub"
  url "https://github.com/hakimjonas/devhub/archive/v0.1.0.tar.gz"
  sha256 "SHA256_PLACEHOLDER" # This will be updated when creating actual releases
  license "MIT"
  head "https://github.com/hakimjonas/devhub.git", branch: "main"

  depends_on "python@3.13"
  depends_on "git"
  depends_on "gh" # GitHub CLI

  # Python dependencies - these will be installed in the virtualenv
  resource "attrs" do
    url "https://files.pythonhosted.org/packages/source/a/attrs/attrs-24.2.0.tar.gz"
    sha256 "5cfb1b9148b5b086569baec03f20d7b6bf3bcacc9a42bebf87ffaaca362f6346"
  end

  resource "cattrs" do
    url "https://files.pythonhosted.org/packages/source/c/cattrs/cattrs-24.1.2.tar.gz"
    sha256 "8028cfe1ff5382df59dd36474a86e02d817b06eaf8af84555441bac915d2ef85"
  end

  resource "returns" do
    url "https://files.pythonhosted.org/packages/source/r/returns/returns-0.23.0.tar.gz"
    sha256 "b1909f35105719b2fbab4b31ba6ed4fb3b6b24b7b8f17edb1d7eb15b2ec2a8d5"
  end

  resource "typing-extensions" do
    url "https://files.pythonhosted.org/packages/source/t/typing_extensions/typing_extensions-4.12.2.tar.gz"
    sha256 "1a7ead55c7e559dd4dee8856e3a88b41225abfe1ce8df57b7c13915fe121ffb8"
  end

  resource "result" do
    url "https://files.pythonhosted.org/packages/source/r/result/result-0.17.0.tar.gz"
    sha256 "58c5a6ca1d8db24d0c7b0b75b0b8b2e076cc098fff82e1d4fea92fda92830c3e"
  end

  resource "toolz" do
    url "https://files.pythonhosted.org/packages/source/t/toolz/toolz-0.12.1.tar.gz"
    sha256 "ecca342664893f177a13dac0e6b41cbd8ac25a358e5f215316d43e2100301ef8"
  end

  resource "immutables" do
    url "https://files.pythonhosted.org/packages/source/i/immutables/immutables-0.20.tar.gz"
    sha256 "1d2f83e6a6a8455466cd97b9a90e2b48dc3fb3138a05c93a0b4c5bb9e6ed07b"
  end

  def install
    # Create virtualenv and install dependencies
    virtualenv_install_with_resources

    # Install DevHub itself
    system libexec/"bin/pip", "install", "--no-deps", "."

    # Create wrapper scripts
    (bin/"devhub").write_env_script libexec/"bin/devhub", PATH: "#{Formula["gh"].opt_bin}:#{Formula["git"].opt_bin}:$PATH"
    (bin/"devhub-mcp").write_env_script libexec/"bin/devhub-mcp", PATH: "#{Formula["gh"].opt_bin}:#{Formula["git"].opt_bin}:$PATH"
  end

  test do
    # Test version command
    assert_match "devhub 0.1.0", shell_output("#{bin}/devhub --version")
    
    # Test help command
    assert_match "Bundle Jira + GitHub PR info", shell_output("#{bin}/devhub --help")
    
    # Test doctor command (should work even without git repo)
    system bin/"devhub", "doctor"
    
    # Test MCP server entry point exists
    assert_predicate bin/"devhub-mcp", :exist?
  end
end