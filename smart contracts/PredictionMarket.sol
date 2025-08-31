// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract PredictionMarket is Ownable, ReentrancyGuard {
    IERC20 public immutable predictionToken;

    // The trusted address that can report match results (our AWS Lambda wallet)
    address public oracle;

    enum Prediction { HOME_TEAM, AWAY_TEAM, DRAW }
    enum MarketStatus { PENDING, OPEN, CLOSED, SETTLED }

    struct Match {
        uint256 matchId; // The ID from football-data.org
        MarketStatus status;
        Prediction result;
        uint256 potHome;
        uint256 potAway;
        uint256 potDraw;
        uint256 totalPot;
    }

    struct Bet {
        address user;
        Prediction prediction;
        uint256 amount;
    }

    mapping(uint256 => Match) public markets;
    mapping(uint256 => mapping(address => Bet)) public bets;

    event MarketCreated(uint256 matchId);
    event BetPlaced(uint256 matchId, address indexed user, Prediction prediction, uint256 amount);
    event ResultReported(uint256 matchId, Prediction result);
    event WinningsClaimed(uint256 matchId, address indexed user, uint256 amount);

    constructor(address _tokenAddress) Ownable(msg.sender) {
        predictionToken = IERC20(_tokenAddress);
        oracle = msg.sender; // Initially, the deployer is the oracle
    }

    modifier onlyOracle() {
        require(msg.sender == oracle, "Only the oracle can call this function");
        _;
    }

    function setOracle(address _newOracle) public onlyOwner {
        oracle = _newOracle;
    }

    // Called by the Oracle (AWS Lambda) to open a new market
    function createMarket(uint256 _matchId) external onlyOracle {
        require(markets[_matchId].matchId == 0, "Market already exists");
        markets[_matchId] = Match({
            matchId: _matchId,
            status: MarketStatus.OPEN,
            result: Prediction.HOME_TEAM, // Default, will be updated
            potHome: 0,
            potAway: 0,
            potDraw: 0,
            totalPot: 0
        });
        emit MarketCreated(_matchId);
    }
    
    // Called by a user to place a bet
    function placeBet(uint256 _matchId, Prediction _prediction, uint256 _amount) external nonReentrant {
        require(_amount > 0, "Amount must be greater than zero");
        Match storage currentMarket = markets[_matchId];
        require(currentMarket.status == MarketStatus.OPEN, "Market is not open");
        require(bets[_matchId][msg.sender].amount == 0, "User has already bet on this match");

        // Transfer tokens from user to this contract for escrow
        bool success = predictionToken.transferFrom(msg.sender, address(this), _amount);
        require(success, "Token transfer failed. Did you approve the contract?");

        // Update pots
        if (_prediction == Prediction.HOME_TEAM) currentMarket.potHome += _amount;
        else if (_prediction == Prediction.AWAY_TEAM) currentMarket.potAway += _amount;
        else currentMarket.potDraw += _amount;
        currentMarket.totalPot += _amount;
        
        // Record bet
        bets[_matchId][msg.sender] = Bet(msg.sender, _prediction, _amount);

        emit BetPlaced(_matchId, msg.sender, _prediction, _amount);
    }
    
    // Called by the Oracle (AWS Lambda) to report the final outcome
    function reportResult(uint256 _matchId, Prediction _result) external onlyOracle {
        require(markets[_matchId].status == MarketStatus.OPEN, "Market is not open");
        markets[_matchId].status = MarketStatus.SETTLED;
        markets[_matchId].result = _result;
        emit ResultReported(_matchId, _result);
    }

    // Called by winning users to claim their share of the pot
    function claimWinnings(uint256 _matchId) external nonReentrant {
        Match storage currentMarket = markets[_matchId];
        require(currentMarket.status == MarketStatus.SETTLED, "Market is not settled");
        
        Bet storage userBet = bets[_matchId][msg.sender];
        require(userBet.amount > 0, "You did not place a bet on this match");
        require(userBet.prediction == currentMarket.result, "Your prediction was not correct");

        uint256 winningPot;
        if (currentMarket.result == Prediction.HOME_TEAM) winningPot = currentMarket.potHome;
        else if (currentMarket.result == Prediction.AWAY_TEAM) winningPot = currentMarket.potAway;
        else winningPot = currentMarket.potDraw;

        require(winningPot > 0, "Winning pot is zero");

        // Calculate payout: (User's Bet / Total Winning Pool) * Total Pot
        uint256 payout = (userBet.amount * currentMarket.totalPot) / winningPot;

        // Reset user's bet amount to prevent re-claiming
        userBet.amount = 0;

        // Transfer winnings to the user
        predictionToken.transfer(msg.sender, payout);
        emit WinningsClaimed(_matchId, msg.sender, payout);
    }
}