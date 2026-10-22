require "./spec_helper"

describe Icon::Octicons do
  it "provides every generated image" do
    {% for constant in Icon::Octicons.constants %}
      Icon::Octicons::{{ constant.id }}.bounds.width.should be > 0
      Icon::Octicons::{{ constant.id }}.bounds.height.should be > 0
    {% end %}
    {{ Icon::Octicons.constants.size }}.should eq(774)
  end

  it "exposes the documented variants with correct dimensions" do
    Icon::Octicons::Heart16.bounds.width.should eq(16)
    Icon::Octicons::LockupGithub16.bounds.width.should eq(68)
    Icon::Octicons::Heart16.at(0, 0).rgba[3].should eq(0)
  end
end
